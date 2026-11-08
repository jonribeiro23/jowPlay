import threading
import unittest
from pathlib import Path

from tests.fakes import FakeCovers
from ytdown.application.extraction import ExtractBatch
from ytdown.domain.errors import ExtractionCancelled, ExtractionError, InvalidCover
from ytdown.domain.models import AUDIO_FORMATS, AudioMetadata, Progress, Stage

MP3 = AUDIO_FORMATS[0]
DESTINATION = object()  # O ExtractBatch só repassa o destino a cada extração.


class FakeExtract:
    """Faz o que `outcomes[url]` mandar: devolver um nome, levantar uma exceção ou chamar uma função."""

    def __init__(self, outcomes: dict) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, AudioMetadata]] = []
        self.destinations: list = []

    def __call__(self, url, destination, audio_format, metadata, on_progress, cancel):
        self.calls.append((url, metadata))
        self.destinations.append(destination)
        on_progress(Progress(Stage.DOWNLOADING, 50))
        outcome = self.outcomes[url]
        if callable(outcome):
            outcome = outcome()
        if isinstance(outcome, BaseException):
            raise outcome
        return Path(outcome)


class ExtractBatchTests(unittest.TestCase):
    def run_batch(self, outcomes, cancel=None, metadata=AudioMetadata(), covers=None, number_tracks=False):
        self.extract = FakeExtract(outcomes)
        self.progress, self.reported = [], []
        batch = ExtractBatch(self.extract, covers or FakeCovers())
        return batch(
            list(outcomes),
            DESTINATION,
            MP3,
            metadata,
            on_progress=lambda index, progress: self.progress.append((index, progress.stage)),
            on_result=lambda index, result: self.reported.append((index, result)),
            cancel=cancel or threading.Event(),
            number_tracks=number_tracks,
        )

    # --- numeração na ordem da lista (JOW-20)

    def test_numbering_follows_the_order_of_the_list(self):
        metadata = AudioMetadata(album="Disco", genre="Rock", year=2024)
        self.run_batch({"u1": "a.mp3", "u2": "b.mp3", "u3": "c.mp3"}, metadata=metadata, number_tracks=True)
        self.assertEqual([(m.track_no, m.album, m.genre, m.year) for _, m in self.extract.calls],
                         [(1, "Disco", "Rock", 2024), (2, "Disco", "Rock", 2024), (3, "Disco", "Rock", 2024)])

    def test_numbering_starts_at_the_chosen_number(self):
        self.run_batch({"u1": "a.mp3", "u2": "b.mp3"}, metadata=AudioMetadata(track_no=7), number_tracks=True)
        self.assertEqual([m.track_no for _, m in self.extract.calls], [7, 8])

    def test_a_failed_video_keeps_its_number_so_the_others_stay_in_place(self):
        results = self.run_batch({"u1": "a.mp3", "u2": ExtractionError("indisponível"), "u3": "c.mp3"},
                                 number_tracks=True)
        self.assertEqual([m.track_no for _, m in self.extract.calls], [1, 2, 3])
        self.assertEqual(results[1].error, "indisponível")

    def test_numbering_does_not_change_a_single_video(self):
        self.run_batch({"u1": "a.mp3"}, metadata=AudioMetadata(track_no=4), number_tracks=True)
        self.assertEqual(self.extract.calls[0][1].track_no, 4)

    def test_without_numbering_videos_of_a_queue_have_no_number(self):
        self.run_batch({"u1": "a.mp3", "u2": "b.mp3"}, metadata=AudioMetadata(track_no=4))
        self.assertEqual([m.track_no for _, m in self.extract.calls], [None, None])

    def test_extracts_every_url_in_order(self):
        results = self.run_batch({"u1": "a.mp3", "u2": "b.mp3"})
        self.assertEqual([r.path for r in results], [Path("a.mp3"), Path("b.mp3")])
        self.assertEqual([url for url, _ in self.extract.calls], ["u1", "u2"])
        self.assertEqual(self.progress, [(0, Stage.DOWNLOADING), (1, Stage.DOWNLOADING)])
        self.assertEqual([index for index, _ in self.reported], [0, 1])
        self.assertEqual(self.extract.destinations, [DESTINATION, DESTINATION])

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
