import tempfile
import threading
import unittest
from pathlib import Path

from tests.fakes import DEFAULT_COVER, SOURCE_URL, FakeCovers, FakeDownloader, FakeTags
from ytdown.application.extraction import ExtractAudio
from ytdown.domain.errors import ExtractionCancelled, ExtractionError, InvalidCover
from ytdown.domain.models import AUDIO_FORMATS, AudioMetadata, AudioTags, Stage

MP3 = AUDIO_FORMATS[0]


class RecordingDestination:
    """Destino de teste: move o arquivo para `folder` e anota o que recebeu."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.received: list[tuple[str, AudioTags]] = []

    def save(self, file: Path, tags: AudioTags) -> Path:
        self.received.append((file.name, tags))
        target = self.folder / file.name
        file.replace(target)
        return target


class ExtractAudioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dest = Path(temp.name)
        self.destination = RecordingDestination(self.dest)
        self.downloader = FakeDownloader()
        self.covers = FakeCovers()
        self.tags = FakeTags()
        self.extract = ExtractAudio(self.downloader, self.covers, self.tags)
        self.stages = []

    def run_extract(self, metadata=AudioMetadata(), cancel=None):
        return self.extract(
            "https://youtu.be/x",
            self.destination,
            MP3,
            metadata,
            lambda progress: self.stages.append(progress.stage),
            cancel or threading.Event(),
        )

    def test_hands_the_tagged_file_to_the_destination(self):
        path = self.run_extract()
        self.assertEqual(path, self.dest / "video.mp3")
        self.assertEqual(path.read_bytes(), b"audio")
        self.assertEqual(self.stages, [Stage.DOWNLOADING, Stage.TAGGING, Stage.SAVING])
        self.assertEqual(self.destination.received, self.tags.calls)  # O destino recebe as etiquetas gravadas.

    def test_tags_default_to_video_title_and_default_cover_with_the_source_url(self):
        self.run_extract()
        self.assertEqual(
            self.tags.calls, [("video.mp3", AudioTags(title="video", cover=DEFAULT_COVER, source_url=SOURCE_URL))]
        )

    def test_title_falls_back_to_the_file_name(self):
        self.downloader.title = None
        self.run_extract()
        self.assertEqual(self.tags.calls[0][1].title, "sem-titulo")

    def test_user_metadata_goes_to_the_tags(self):
        cover = Path("capa.png")
        self.covers.valid.add(cover)
        metadata = AudioMetadata(
            title="Meu nome", artist="Eu", cover=cover, album="Disco", genre="MPB", year=2024, track_no=3
        )
        self.run_extract(metadata)
        expected = AudioTags(
            title="Meu nome", cover=b"capa:capa.png", artist="Eu", album="Disco", genre="MPB", year=2024,
            track_no=3, source_url=SOURCE_URL,
        )
        self.assertEqual(self.tags.calls, [("video.mp3", expected)])

    def test_invalid_cover_fails_before_downloading(self):
        with self.assertRaises(InvalidCover):
            self.run_extract(AudioMetadata(cover=Path("nao-existe.png")))
        self.assertEqual(self.downloader.calls, [])

    def test_cancel_during_download_saves_nothing(self):
        cancel = threading.Event()
        self.downloader.on_download = cancel.set
        with self.assertRaises(ExtractionCancelled):
            self.run_extract(cancel=cancel)
        self.assertEqual(self.destination.received, [])
        self.assertEqual(self.tags.calls, [])

    def test_download_failure_saves_nothing(self):
        self.downloader.error = ExtractionError("indisponível")
        with self.assertRaisesRegex(ExtractionError, "indisponível"):
            self.run_extract()
        self.assertEqual(self.destination.received, [])


if __name__ == "__main__":
    unittest.main()
