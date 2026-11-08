import threading
import unittest
from pathlib import Path

from tests.fakes import FakeCovers
from ytdown.application.extraction import ExtractBatch
from ytdown.domain.errors import ExtractionCancelled, ExtractionError, InvalidCover
from ytdown.domain.models import AUDIO_FORMATS, AudioMetadata, Progress, Stage

MP3 = AUDIO_FORMATS[0]


class FakeExtract:
    """Faz o que `outcomes[url]` mandar: devolver um nome, levantar uma exceção ou chamar uma função."""

    def __init__(self, outcomes: dict) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, AudioMetadata]] = []

    def __call__(self, url, dest, audio_format, metadata, on_progress, cancel):
        self.calls.append((url, metadata))
        on_progress(Progress(Stage.DOWNLOADING, 50))
        outcome = self.outcomes[url]
        if callable(outcome):
            outcome = outcome()
        if isinstance(outcome, BaseException):
            raise outcome
        return Path(outcome)


class ExtractBatchTests(unittest.TestCase):
    def run_batch(self, outcomes, cancel=None, metadata=AudioMetadata(), covers=None):
        self.extract = FakeExtract(outcomes)
        self.progress, self.reported = [], []
        batch = ExtractBatch(self.extract, covers or FakeCovers())
        return batch(
            list(outcomes),
            Path("destino"),
            MP3,
            metadata,
            on_progress=lambda index, progress: self.progress.append((index, progress.stage)),
            on_result=lambda index, result: self.reported.append((index, result)),
            cancel=cancel or threading.Event(),
        )

    def test_extracts_every_url_in_order(self):
        results = self.run_batch({"u1": "a.mp3", "u2": "b.mp3"})
        self.assertEqual([r.path for r in results], [Path("a.mp3"), Path("b.mp3")])
        self.assertEqual([url for url, _ in self.extract.calls], ["u1", "u2"])
        self.assertEqual(self.progress, [(0, Stage.DOWNLOADING), (1, Stage.DOWNLOADING)])
        self.assertEqual([index for index, _ in self.reported], [0, 1])

    def test_a_failure_does_not_stop_the_rest(self):
        results = self.run_batch({"u1": ExtractionError("indisponível"), "u2": RuntimeError("estranho"), "u3": "c.mp3"})
        self.assertEqual(results[0].error, "indisponível")
        self.assertIn("estranho", results[1].error)
        self.assertEqual(results[2].path, Path("c.mp3"))

    def test_cancel_stops_current_and_marks_the_rest(self):
        cancel = threading.Event()

        def cancelled_while_downloading():
            cancel.set()
            return ExtractionCancelled()

        results = self.run_batch({"u1": "a.mp3", "u2": cancelled_while_downloading, "u3": "c.mp3"}, cancel=cancel)
        self.assertEqual(results[0].path, Path("a.mp3"))
        self.assertTrue(results[1].cancelled and results[2].cancelled)
        self.assertEqual([url for url, _ in self.extract.calls], ["u1", "u2"])  # u3 nem começou.
        self.assertEqual(len(self.reported), 3)

    def test_shared_details_go_to_every_video(self):
        cover = Path("capa.png")
        metadata = AudioMetadata(artist="Banda", cover=cover, album="Disco", genre="Rock", year=2024)
        self.run_batch({"u1": "a.mp3", "u2": "b.mp3"}, metadata=metadata, covers=FakeCovers({cover}))
        self.assertEqual([meta for _, meta in self.extract.calls], [metadata, metadata])

    def test_with_several_videos_each_one_keeps_its_own_title_and_number(self):
        metadata = AudioMetadata(title="Mesmo nome", track_no=5, album="Disco")
        self.run_batch({"u1": "a.mp3", "u2": "b.mp3"}, metadata=metadata)
        self.assertEqual([(m.title, m.track_no, m.album) for _, m in self.extract.calls], [("", None, "Disco")] * 2)

    def test_with_a_single_video_the_chosen_title_and_number_are_used(self):
        self.run_batch({"u1": "a.mp3"}, metadata=AudioMetadata(title="Meu nome", track_no=5))
        self.assertEqual((self.extract.calls[0][1].title, self.extract.calls[0][1].track_no), ("Meu nome", 5))

    def test_invalid_cover_fails_once_before_any_download(self):
        with self.assertRaises(InvalidCover):
            self.run_batch({"u1": "a.mp3"}, metadata=AudioMetadata(cover=Path("nao-existe.png")))
        self.assertEqual(self.extract.calls, [])


if __name__ == "__main__":
    unittest.main()
