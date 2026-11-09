import io
import tempfile
import threading
import unittest
import wave
from pathlib import Path

from mutagen.id3 import APIC
from mutagen.wave import WAVE
from PIL import Image

from ytdown.infrastructure.metadata_reader import MutagenMetadataReader
from ytdown.infrastructure.thumbnails import FileThumbnailCache


def cover(color):
    output = io.BytesIO()
    Image.new('RGB', (400, 300), color).save(output, format='PNG')
    return output.getvalue()


def audio(path, data):
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\0\0' * 100)
    sound = WAVE(path)
    sound.add_tags()
    sound.tags.add(APIC(mime='image/png', type=3, data=data))
    sound.save()


class ThumbnailIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = FileThumbnailCache(MutagenMetadataReader(), self.root / 'thumbs')
        self.addCleanup(self.cache.close)

    def test_generate_reuse_edit_and_cleanup(self):
        a, b = self.root / 'a.wav', self.root / 'b.wav'
        audio(a, cover('red'))
        audio(b, cover('red'))
        first = self.cache.get_or_create(a)
        self.assertEqual(first, self.cache.get_or_create(b))
        with Image.open(first) as image:
            self.assertEqual(image.size, (200, 150))
        sound = WAVE(a)
        sound.tags.delall('APIC')
        sound.tags.add(APIC(mime='image/png', type=3, data=cover('blue')))
        sound.save()
        second = self.cache.get_or_create(a)
        self.assertNotEqual(first, second)
        self.assertEqual(self.cache.cleanup([a, b]), 0)
        self.assertEqual(self.cache.cleanup([a]), 1)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())

    def test_cleanup_aborts_on_unreadable_audio(self):
        a = self.root / 'a.wav'
        audio(a, cover('red'))
        target = self.cache.get_or_create(a)
        with self.assertRaises(Exception):
            self.cache.cleanup([self.root / 'missing.wav'])
        self.assertTrue(target.exists())

    def test_request_does_not_wait_for_slow_reader(self):
        entered, release = threading.Event(), threading.Event()
        class SlowReader:
            def read_cover(self, path):
                entered.set()
                release.wait(5)
                return None
        cache = FileThumbnailCache(SlowReader(), self.root / 'slow')
        self.addCleanup(cache.close)
        cache.request(self.root / 'a.wav')
        self.assertTrue(entered.wait(2))
        returned = threading.Event()
        thread = threading.Thread(target=lambda: (cache.request(self.root / 'b.wav'), returned.set()))
        thread.start()
        self.assertTrue(returned.wait(1))
        release.set()
        thread.join()
        cache._jobs.join()


class ThumbnailFlowTests(unittest.TestCase):
    def test_import_and_registration_schedule_generation(self):
        from ytdown.application.importing import ImportAudios
        from ytdown.application.library import RegisterExtractedTrack
        from ytdown.domain.models import AudioTags
        from ytdown.infrastructure.import_files import FileSystemImportFiles
        from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
        from ytdown.infrastructure.sqlite_library import SqliteTrackRepository

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storage = FileSystemLibraryStorage(root / 'library')
            tracks = SqliteTrackRepository(root / 'index.db')
            cache = FileThumbnailCache(MutagenMetadataReader(), root / 'thumbs')
            try:
                source = root / 'source'
                source.mkdir()
                audio(source / 'import.wav', cover('red'))
                result = ImportAudios(storage, tracks, MutagenMetadataReader(),
                                      FileSystemImportFiles(), cache)([source])
                self.assertEqual(result.imported, 1)
                cache._jobs.join()
                self.assertEqual(len(list(cache.directory.glob('*.png'))), 1)
                extracted = root / 'extracted.wav'
                audio(extracted, cover('blue'))
                RegisterExtractedTrack(storage, tracks, MutagenMetadataReader(), thumbnails=cache)(
                    extracted, AudioTags(title='Outra', cover=cover('blue')))
                cache._jobs.join()
                self.assertEqual(len(list(cache.directory.glob('*.png'))), 2)
            finally:
                cache.close()
                tracks.close()

