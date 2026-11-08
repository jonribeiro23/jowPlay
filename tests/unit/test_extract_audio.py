import tempfile
import threading
import unittest
from pathlib import Path

from tests.fakes import DEFAULT_COVER, FakeCovers, FakeDownloader, FakeTags
from ytdown.application.extraction import ExtractAudio
from ytdown.domain.errors import ExtractionCancelled, ExtractionError, InvalidCover
from ytdown.domain.models import AUDIO_FORMATS, AudioMetadata, Stage

MP3 = AUDIO_FORMATS[0]


class ExtractAudioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dest = Path(temp.name)
        self.downloader = FakeDownloader()
        self.covers = FakeCovers()
        self.tags = FakeTags()
        self.extract = ExtractAudio(self.downloader, self.covers, self.tags)
        self.stages = []

    def run_extract(self, metadata=AudioMetadata(), dest=None, cancel=None):
        return self.extract(
            "https://youtu.be/x",
            dest or self.dest,
            MP3,
            metadata,
            lambda progress: self.stages.append(progress.stage),
            cancel or threading.Event(),
        )

    def test_saves_file_in_destination(self):
        path = self.run_extract()
        self.assertEqual(path, self.dest / "video.mp3")
        self.assertEqual(path.read_bytes(), b"audio")
        self.assertEqual(self.stages, [Stage.DOWNLOADING, Stage.TAGGING, Stage.SAVING])

    def test_metadata_defaults_to_video_title_no_author_and_default_cover(self):
        self.run_extract()
        self.assertEqual(self.tags.calls, [("video.mp3", "video", "", DEFAULT_COVER)])

    def test_title_falls_back_to_the_file_name(self):
        self.downloader.title = None
        self.run_extract()
        self.assertEqual(self.tags.calls[0][1], "sem-titulo")

    def test_user_metadata_replaces_defaults(self):
        cover = Path("capa.png")
        self.covers.valid.add(cover)
        self.run_extract(AudioMetadata(title="Meu nome", author="Eu", cover=cover))
        self.assertEqual(self.tags.calls, [("video.mp3", "Meu nome", "Eu", b"capa:capa.png")])

    def test_invalid_cover_fails_before_downloading(self):
        with self.assertRaises(InvalidCover):
            self.run_extract(AudioMetadata(cover=Path("nao-existe.png")))
        self.assertEqual(self.downloader.calls, [])

    def test_creates_missing_destination(self):
        self.assertTrue(self.run_extract(dest=self.dest / "nova" / "pasta").exists())

    def test_never_overwrites_existing_files(self):
        (self.dest / "video.mp3").write_bytes(b"antigo")
        (self.dest / "video (1).mp3").write_bytes(b"antigo")
        path = self.run_extract()
        self.assertEqual(path.name, "video (2).mp3")
        self.assertEqual((self.dest / "video.mp3").read_bytes(), b"antigo")

    def test_cancel_during_download_saves_nothing(self):
        cancel = threading.Event()
        self.downloader.on_download = cancel.set
        with self.assertRaises(ExtractionCancelled):
            self.run_extract(cancel=cancel)
        self.assertEqual(list(self.dest.iterdir()), [])
        self.assertEqual(self.tags.calls, [])

    def test_download_failure_saves_nothing(self):
        self.downloader.error = ExtractionError("indisponível")
        with self.assertRaisesRegex(ExtractionError, "indisponível"):
            self.run_extract()
        self.assertEqual(list(self.dest.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
