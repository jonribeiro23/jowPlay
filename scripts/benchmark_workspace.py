"""Benchmark isolado: execute com .venv/Scripts/python scripts/benchmark_workspace.py."""
import argparse
import io
import json
import os
import platform
import sys
import tempfile
import time
import wave
from datetime import datetime
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
from mutagen.id3 import APIC, TALB, TIT2, TPE1, TRCK
from mutagen.wave import WAVE
from PySide6 import __version__ as qt_version
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tests.fakes import FakeAudioPlayer
from ytdown.application.importing import ImportAudios
from ytdown.application.library import CheckLibrary, ChangeLibraryFolder, RegisterExtractedTrack
from ytdown.application.playback import Playback
from ytdown.application.playlists import ManagePlaylists
from ytdown.bootstrap import Library, build_main_window
from ytdown.domain.library import Track
from ytdown.infrastructure.import_files import FileSystemImportFiles
from ytdown.infrastructure.json_settings import JsonSettings
from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
from ytdown.infrastructure.metadata_reader import MutagenMetadataReader
from ytdown.infrastructure.sqlite_library import SqliteTrackRepository
from ytdown.infrastructure.sqlite_playlists import SqlitePlaylistRepository
from ytdown.infrastructure.thumbnails import FileThumbnailCache
from ytdown.presentation.qt.pages import PageId


def generate(root, repo, count):
    """Todos os caminhos são descendentes da raiz temporária criada pelo chamador."""
    root.mkdir()
    for i in range(count):
        album, artist = i % 500, (i % 500) % 300
        path = root / f'{i:05}.wav'
        with wave.open(str(path), 'wb') as audio:
            audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\0\0' * 800)
        image = Image.new('RGB', (32, 32), (album % 256, album // 256 * 100, album * 37 % 256))
        data = io.BytesIO()
        image.save(data, format='PNG')
        wav = WAVE(path)
        wav.add_tags()
        wav.tags.add(TIT2(encoding=3, text=[f'Faixa {i:05}']))
        wav.tags.add(TPE1(encoding=3, text=[f'Artista {artist:03}']))
        wav.tags.add(TALB(encoding=3, text=[f'Album {album:03}']))
        wav.tags.add(TRCK(encoding=3, text=[str(i // 500 + 1)]))
        wav.tags.add(APIC(encoding=3, mime='image/png', type=3, data=data.getvalue()))
        wav.save()
        repo.add(Track(rel_path=path.name, title=f'Faixa {i:05}', artist=f'Artista {artist:03}',
                       album=f'Album {album:03}', genre=f'Genero {i % 10}',
                       track_no=i // 500 + 1, duration_ms=100, added_at=datetime(2020, 1, 1)))


def run(count=5000, imports=10):
    app = QApplication.instance() or QApplication([])
    result = {'environment': {'platform': platform.platform(), 'processor': platform.processor(),
              'logical_cpus': os.cpu_count(), 'python': platform.python_version(), 'pyside': qt_version,
              'qt_platform': 'offscreen'}, 'count': count, 'seconds': {}}
    times = result['seconds']
    def measure(name, action):
        start = time.perf_counter()
        value = action()
        app.processEvents()
        times[name] = round(time.perf_counter() - start, 4)
        return value
    with tempfile.TemporaryDirectory(prefix='ytdown-benchmark-') as directory:
        base = Path(directory)
        repo = SqliteTrackRepository(base / 'library.db')
        measure('generate', lambda: generate(base / 'audio', repo, count))
        reader = MutagenMetadataReader()
        settings = JsonSettings(base / 'settings.json')
        storage = FileSystemLibraryStorage(base / 'audio')
        cache = FileThumbnailCache(reader, base / 'thumbs')
        library = Library(RegisterExtractedTrack(storage, repo, reader, thumbnails=cache),
                          ChangeLibraryFolder(storage, repo, settings), repo, settings, storage, cache,
                          ManagePlaylists(SqlitePlaylistRepository(repo)))
        playback = Playback(FakeAudioPlayer(), storage, tracks=repo)
        class Sharing:
            def send(self, *args): pass
        sharing = Sharing()
        try:
            window = measure('open_construct_show', lambda: build_main_window(library, playback, None, sharing))
            measure('show', window.show)
            for page in PageId:
                measure('page_' + page.name.lower(), lambda p=page: window.show_page(p))
            songs = window.page(PageId.SONGS)
            albums = window.page(PageId.ALBUMS)
            def scroll(page, view):
                window.show_page(page)
                bar = view.verticalScrollBar()
                maximum = bar.maximum()
                for step in range(21):
                    bar.setValue(maximum * step // 20)
                    app.processEvents()
                return maximum
            result['scroll_max_songs'] = measure('scroll_songs_20_steps', lambda: scroll(PageId.SONGS, songs.table))
            result['scroll_max_albums'] = measure('scroll_albums_20_steps', lambda: scroll(PageId.ALBUMS, albums.view))
            measure('search_songs', lambda: songs.model.set_search_text('Faixa 000'))
            result['search_matches'] = songs.model.rowCount()
            measure('clear_search', lambda: songs.model.set_search_text(''))
            measure('sort_songs_artist', lambda: songs.model.sort(1, Qt.SortOrder.DescendingOrder))
            measure('sort_albums_artist', lambda: albums.sort.setCurrentIndex(1))
            check = measure('check_library', lambda: CheckLibrary(storage, repo)())
            result['check'] = vars(check)
            source = base / 'import'
            source.mkdir()
            # Arquivos distintos dos existentes: copia WAVs e modifica a etiqueta de título.
            import shutil
            for i in range(min(imports, count)):
                target = source / f'import-{i}.wav'
                shutil.copyfile(storage.root / f'{i:05}.wav', target)
                wav = WAVE(target)
                wav.tags.add(TIT2(encoding=3, text=[f'Importada {i}']))
                wav.save()
            imported = measure('import', lambda: ImportAudios(storage, repo, reader, FileSystemImportFiles())([source]))
            result['import'] = vars(imported)
            result['albums'] = len(albums.model.albums)
            result['artists'] = len(repo.artists())
            window.close()
            app.processEvents()
        finally:
            cache.close()
            cache._worker.join()
            repo.close()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=5000)
    parser.add_argument('--imports', type=int, default=10)
    args = parser.parse_args()
    if args.count < 1 or args.imports < 0:
        parser.error('count deve ser positivo e imports não negativo')
    print(json.dumps(run(args.count, args.imports), ensure_ascii=False, indent=2))
