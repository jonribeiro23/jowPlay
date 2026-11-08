"""Regras dos campos de álbum da extração: ano, nº da faixa, numeração da fila e gêneros sugeridos."""

import unittest
from datetime import datetime

from tests.fakes import InMemoryTrackRepository
from ytdown.application.extraction import video_metadata
from ytdown.application.library import known_genres
from ytdown.domain.library import Track
from ytdown.domain.models import AudioMetadata, is_valid_track_no, is_valid_year


class ValidationTests(unittest.TestCase):
    def test_year_has_four_digits(self):
        for year in (1000, 1969, 2024, 9999):
            with self.subTest(year):
                self.assertTrue(is_valid_year(year))
        for year in (0, 24, 999, 10000):
            with self.subTest(year):
                self.assertFalse(is_valid_year(year))

    def test_track_number_is_positive(self):
        self.assertTrue(is_valid_track_no(1))
        self.assertTrue(is_valid_track_no(120))
        self.assertFalse(is_valid_track_no(0))
        self.assertFalse(is_valid_track_no(-3))


class VideoMetadataTests(unittest.TestCase):
    ALBUM = AudioMetadata(title="Nome", artist="Banda", album="Disco", genre="Rock", year=2024, track_no=None)

    def test_a_single_video_keeps_everything(self):
        chosen = AudioMetadata(title="Nome", track_no=4)
        self.assertEqual(video_metadata(chosen, 0, 1, number_tracks=True), chosen)

    def test_numbered_queue(self):
        numbers = [video_metadata(self.ALBUM, i, 3, number_tracks=True).track_no for i in range(3)]
        self.assertEqual(numbers, [1, 2, 3])

    def test_numbered_queue_from_a_chosen_start(self):
        start = AudioMetadata(track_no=10)
        self.assertEqual([video_metadata(start, i, 2, number_tracks=True).track_no for i in range(2)], [10, 11])

    def test_queue_videos_use_their_own_title_and_share_the_rest(self):
        own = video_metadata(self.ALBUM, 1, 3)
        self.assertEqual((own.title, own.track_no), ("", None))
        self.assertEqual((own.artist, own.album, own.genre, own.year), ("Banda", "Disco", "Rock", 2024))


class KnownGenresTests(unittest.TestCase):
    def test_existing_genres_without_the_unknown_one(self):
        tracks = InMemoryTrackRepository()
        for title, genre in (("a", "Rock"), ("b", ""), ("c", "MPB"), ("d", "rock")):
            tracks.add(Track(rel_path=f"x/{title}.mp3", title=title, added_at=datetime(2026, 1, 1), genre=genre))
        self.assertEqual(known_genres(tracks), ["MPB", "Rock"])

    def test_empty_library(self):
        self.assertEqual(known_genres(InMemoryTrackRepository()), [])


if __name__ == "__main__":
    unittest.main()
