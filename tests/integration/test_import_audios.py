import shutil
import subprocess
import tempfile
import unittest
import wave
from dataclasses import replace
from pathlib import Path
from threading import Event
from unittest.mock import patch

from ytdown.application.importing import ImportAudios
from ytdown.bootstrap import build_library
from ytdown.infrastructure.import_files import FileSystemImportFiles, CHUNK_SIZE
from ytdown.infrastructure.metadata_reader import MutagenMetadataReader


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'old'
        self.source.mkdir()
        self.library = build_library(self.root/'index.db', self.root/'settings.json', self.root/'managed')
        self.addCleanup(self.library.close)
        self.files = FileSystemImportFiles()
        self.job = ImportAudios(self.library.storage, self.library.tracks, MutagenMetadataReader(), self.files)

    def audio(self, name='song.wav', frames=1000):
        path = self.source/name
        with wave.open(str(path), 'wb') as output:
            output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            output.writeframes(b'\x00\x01'*frames)
        return path

    def test_valid_duplicates_corrupt_overlapping_roots_and_repeat(self):
        source = self.audio()
        original = source.read_bytes()
        shutil.copyfile(source, self.source/'duplicate.WAV')
        (self.source/'bad.mp3').write_bytes(b'broken')
        result = self.job([self.root, self.source])
        self.assertEqual((result.imported, result.duplicates, len(result.errors)), (1, 1, 1))
        track = self.library.tracks.list_tracks()[0]
        self.assertEqual(self.library.storage.absolute(track.rel_path).read_bytes(), original)
        self.assertIsNone(track.source_url)
        self.assertEqual(source.read_bytes(), original)
        result = self.job([self.root])
        self.assertEqual((result.imported, result.duplicates), (0, 2))

    def test_url_canonical_against_existing_and_batch(self):
        self.audio('a.wav', 1000)
        self.audio('b.wav', 2000)
        reader = MutagenMetadataReader()
        class WithUrl:
            calls = 0
            def read(self, path):
                self.calls += 1
                url = ('https://youtu.be/jNQXAC9IVRw' if self.calls % 2
                       else 'https://www.youtube.com/watch?v=jNQXAC9IVRw')
                return replace(reader.read(path), source_url=url)
        self.job.reader = WithUrl()
        result = self.job([self.source])
        self.assertEqual((result.imported, result.duplicates), (1, 1))
        result = self.job([self.source])
        self.assertEqual((result.imported, result.duplicates), (0, 2))

    def test_cancel_during_copy_cleans_staging_and_keeps_original(self):
        source = self.audio(frames=CHUNK_SIZE*2)
        original = source.read_bytes()
        cancel = Event()
        ticks = []
        def progress(phase, done, total):
            if phase.startswith('Copiando'):
                ticks.append(phase)
                if len(ticks) == 2:
                    cancel.set()
        result = self.job([self.source], cancel, progress)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.imported, 0)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.library.storage.root.iterdir()), [])

    def test_cancel_after_first_import_keeps_completed_track(self):
        self.audio('a.wav', 1000)
        self.audio('b.wav', 2000)
        cancel = Event()
        def progress(phase, done, total):
            if phase == 'Importando' and done == 1:
                cancel.set()
        result = self.job([self.source], cancel, progress)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.imported, 1)
        self.assertEqual(len(self.library.tracks.list_tracks()), 1)
        self.assertFalse(list(self.library.storage.root.glob('.ytdown-import-*')))

    def test_cancel_scan_and_existing_hash(self):
        self.audio()
        cancel = Event()
        result = self.job([self.source], cancel, lambda *args: cancel.set())
        self.assertTrue(result.cancelled)
        self.job([self.source])
        cancel.clear()
        def progress(phase, *args):
            if phase.startswith('Verificando duplicatas'):
                cancel.set()
        result = self.job([self.source], cancel, progress)
        self.assertTrue(result.cancelled)

    def test_unreadable_existing_aborts_before_copy(self):
        self.audio()
        self.job([self.source])
        self.audio('other.wav', 2000)
        with patch.object(self.files, 'fingerprint', side_effect=PermissionError('denied')):
            result = self.job([self.source])
        self.assertEqual(result.imported, 0)
        self.assertEqual(len(result.errors), 1)

    def test_repository_failure_discards_file(self):
        self.audio()
        with patch.object(self.library.tracks, 'add', side_effect=ValueError('index failed')):
            result = self.job([self.source])
        self.assertEqual(len(result.errors), 1)
        self.assertFalse(list(self.library.storage.root.rglob('*.wav')))
        self.assertFalse(list(self.library.storage.root.glob('.ytdown-import-*')))

    @unittest.skipUnless(shutil.which('ffmpeg'), 'requires ffmpeg')
    def test_all_four_real_formats(self):
        for index, ext in enumerate(('mp3', 'm4a', 'flac', 'wav')):
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                f'sine=frequency={400+index*100}:duration=0.1', str(self.source/f'a.{ext}')], check=True)
        result = self.job([self.source])
        self.assertEqual((result.imported, result.duplicates, result.errors), (4, 0, []))

    def test_cancel_after_place_rolls_back(self):
        self.audio()
        cancel = Event()
        place = self.library.storage.place
        def cancelling_place(*args):
            placed = place(*args)
            cancel.set()
            return placed
        with patch.object(self.library.storage, 'place', side_effect=cancelling_place):
            result = self.job([self.source], cancel)
        self.assertTrue(result.cancelled)
        self.assertEqual(self.library.tracks.list_tracks(), [])
        self.assertFalse(list(self.library.storage.root.rglob('*.wav')))
        self.assertFalse(list(self.library.storage.root.glob('.ytdown-import-*')))

    def test_cancel_cleanup_failure_reports_residual(self):
        self.audio()
        cancel = Event()
        place = self.library.storage.place
        def cancelling_place(*args):
            placed = place(*args)
            cancel.set()
            return placed
        with patch.object(self.library.storage, 'place', side_effect=cancelling_place), \
             patch.object(self.library.storage, 'discard', side_effect=PermissionError('locked')):
            result = self.job([self.source], cancel)
        self.assertTrue(result.cancelled)
        self.assertIn('destino residual', result.errors[0])
        self.assertIn('locked', result.errors[0])
        self.assertEqual(self.library.tracks.list_tracks(), [])
        self.assertFalse(list(self.library.storage.root.glob('.ytdown-import-*')))

    def test_scan_junction_and_errors(self):
        self.audio()
        sub = self.source/'junction'
        sub.mkdir()
        shutil.copyfile(self.source/'song.wav', sub/'hidden.wav')
        with patch.object(Path, 'is_junction', lambda path: path.name == 'junction'):
            paths, errors = self.files.scan([self.source], self.library.storage.root, Event(), lambda: None)
        self.assertEqual(paths, [self.source/'song.wav'])
        self.assertEqual(errors, [])
        def walk(*args, **kwargs):
            kwargs['onerror'](PermissionError('unreadable directory'))
            return iter([])
        with patch('ytdown.infrastructure.import_files.os.walk', side_effect=walk):
            paths, errors = self.files.scan([self.source], self.library.storage.root, Event(), lambda: None)
        self.assertIn('unreadable directory', errors[0])

    def test_real_tags_and_cover_preserved(self):
        from ytdown.infrastructure.tags import MutagenTagWriter
        from ytdown.domain.models import AudioTags
        from ytdown.infrastructure.covers import PillowCoverLoader
        from ytdown.infrastructure.resources import asset
        source = self.audio()
        cover = PillowCoverLoader(asset('default_cover.jpg')).load(None)
        MutagenTagWriter().write(source, AudioTags(title='Title', artist='Artist', album='Album',
            genre='Rock', year=2020, track_no=3, cover=cover))
        original = source.read_bytes()
        expected = MutagenMetadataReader().read(source)
        result = self.job([self.source])
        self.assertEqual(result.imported, 1)
        track = self.library.tracks.list_tracks()[0]
        self.assertEqual((track.title, track.artist, track.album, track.genre, track.year, track.track_no,
                          track.duration_ms), ('Title', 'Artist', 'Album', 'Rock', 2020, 3, expected.duration_ms))
        target = self.library.storage.absolute(track.rel_path)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(MutagenMetadataReader().read_cover(target), cover)


if __name__ == '__main__':
    unittest.main()
