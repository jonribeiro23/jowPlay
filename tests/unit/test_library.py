import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime

from ytdown.domain import library
from ytdown.domain.library import (
    UNKNOWN_ALBUM,
    UNKNOWN_ARTIST,
    UNKNOWN_GENRE,
    AlbumSummary,
    SortField,
    Track,
    TrackQuery,
)

DAY = datetime(2026, 11, 1)


def track(title="Faixa", id=None, **fields) -> Track:
    return Track(rel_path=f"{title}.mp3", title=title, added_at=fields.pop("added_at", DAY), id=id, **fields)


class TrackTests(unittest.TestCase):
    def test_missing_values_have_display_names(self):
        empty = track(artist="  ", album="", genre="")
        self.assertEqual(
            (empty.display_artist, empty.display_album, empty.display_genre),
            (UNKNOWN_ARTIST, UNKNOWN_ALBUM, UNKNOWN_GENRE),
        )

    def test_display_names_trim_spaces(self):
        self.assertEqual(track(artist=" Ana ").display_artist, "Ana")

    def test_tracks_are_immutable_and_changed_by_copy(self):
        original = track(play_count=1)
        with self.assertRaises(FrozenInstanceError):
            original.play_count = 2
        self.assertEqual(replace(original, play_count=2).play_count, 2)


class AlbumOrderTests(unittest.TestCase):
    def test_by_track_number_then_title_with_unnumbered_last(self):
        tracks = [track("Zeta"), track("B", track_no=2), track("Alfa"), track("A", track_no=1)]
        self.assertEqual([t.title for t in library.album_order(tracks)], ["A", "B", "Alfa", "Zeta"])


class SummaryTests(unittest.TestCase):
    def test_albums_with_same_name_but_different_artists_stay_apart(self):
        tracks = [track("1", id=1, album="Sol", artist="Ana"), track("2", id=2, album="Sol", artist="Bia")]
        self.assertEqual([(a.title, a.artist) for a in library.summarize_albums(tracks)], [("Sol", "Ana"), ("Sol", "Bia")])

    def test_album_totals_year_and_cover(self):
        tracks = [
            track("Dois", id=2, album="Sol", artist="Ana", track_no=2, year=2021, duration_ms=100),
            track("Um", id=1, album="Sol", artist="Ana", track_no=1, year=2020, duration_ms=50),
            track("Sem ano", id=3, album="Sol", artist="Ana", track_no=3, duration_ms=25),
        ]
        self.assertEqual(
            library.summarize_albums(tracks),
            [AlbumSummary("Sol", "Ana", year=2020, track_count=3, total_duration_ms=175, cover_track_id=1)],
        )

    def test_album_without_any_year(self):
        self.assertIsNone(library.summarize_albums([track(album="Sol")])[0].year)

    def test_alphabetical_ignoring_accents_with_unknown_last(self):
        tracks = [track(id=1, album=""), track(id=2, album="Zebra"), track(id=3, album="Álbum"), track(id=4, album="Avião")]
        self.assertEqual([a.title for a in library.summarize_albums(tracks)], ["Álbum", "Avião", "Zebra", UNKNOWN_ALBUM])

    def test_artists_count_albums_tracks_and_duration(self):
        tracks = [
            track("1", id=1, artist="Ana", album="Sol", track_no=1, duration_ms=10),
            track("2", id=2, artist="Ana", album="Sol", track_no=2, duration_ms=20),
            track("3", id=3, artist="Ana", album="Lua", duration_ms=30),
            track("4", id=4, artist="", album="Sol", duration_ms=40),
        ]
        ana, unknown = library.summarize_artists(tracks)
        self.assertEqual((ana.name, ana.album_count, ana.track_count, ana.total_duration_ms), ("Ana", 2, 3, 60))
        self.assertEqual(ana.cover_track_id, 3)  # Primeira faixa do primeiro álbum em ordem alfabética (Lua).
        self.assertEqual((unknown.name, unknown.track_count), (UNKNOWN_ARTIST, 1))

    def test_genres_with_unknown_last(self):
        tracks = [track(genre="Rock", duration_ms=5), track(genre=""), track(genre="MPB"), track(genre="Rock", duration_ms=7)]
        self.assertEqual(
            [(g.name, g.track_count, g.total_duration_ms) for g in library.summarize_genres(tracks)],
            [("MPB", 1, 0), ("Rock", 2, 12), (UNKNOWN_GENRE, 1, 0)],
        )

    def test_genres_differing_only_in_case_are_kept_apart(self):
        # O nome exibido é o que está na etiqueta; unificar grafias é tarefa da edição de propriedades.
        self.assertEqual(len(library.summarize_genres([track(genre="Rock"), track(genre="rock")])), 2)

    def test_empty_library(self):
        self.assertEqual(
            (library.summarize_albums([]), library.summarize_artists([]), library.summarize_genres([])), ([], [], [])
        )


class MatchTests(unittest.TestCase):
    SONG = track("Canção do Mar", artist="João", album="Praia", genre="MPB")

    def test_every_word_must_appear_somewhere(self):
        self.assertTrue(library.matches(self.SONG, TrackQuery(text="cancao joao")))
        self.assertTrue(library.matches(self.SONG, TrackQuery(text="PRAIA mpb")))
        self.assertFalse(library.matches(self.SONG, TrackQuery(text="cancao rock")))

    def test_empty_text_matches_everything(self):
        self.assertTrue(library.matches(self.SONG, TrackQuery(text="   ")))

    def test_filters_use_display_names(self):
        self.assertTrue(library.matches(track(), TrackQuery(artist=UNKNOWN_ARTIST, album=UNKNOWN_ALBUM)))
        self.assertFalse(library.matches(self.SONG, TrackQuery(artist=UNKNOWN_ARTIST)))
        self.assertTrue(library.matches(self.SONG, TrackQuery(artist="João", genre="MPB")))

    def test_missing_tracks_can_be_hidden(self):
        missing = track(missing=True)
        self.assertTrue(library.matches(missing, TrackQuery()))
        self.assertFalse(library.matches(missing, TrackQuery(include_missing=False)))


class SortTests(unittest.TestCase):
    def titles(self, tracks):
        return [t.title for t in tracks]

    def test_sort_by_title_ignoring_accents(self):
        tracks = [track("Zebra"), track("Ávore"), track("Abelha")]
        self.assertEqual(self.titles(library.sort_tracks(tracks, SortField.TITLE)), ["Abelha", "Ávore", "Zebra"])

    def test_empty_values_stay_last_in_both_directions(self):
        tracks = [track("Sem ano"), track("Velha", year=1990), track("Nova", year=2020)]
        self.assertEqual(self.titles(library.sort_tracks(tracks, SortField.YEAR)), ["Velha", "Nova", "Sem ano"])
        self.assertEqual(
            self.titles(library.sort_tracks(tracks, SortField.YEAR, descending=True)), ["Nova", "Velha", "Sem ano"]
        )

    def test_ties_follow_album_order(self):
        tracks = [
            track("B2", artist="B", album="X", track_no=2, play_count=1),
            track("A1", artist="A", album="X", track_no=1, play_count=1),
            track("B1", artist="B", album="X", track_no=1, play_count=1),
        ]
        self.assertEqual(self.titles(library.sort_tracks(tracks, SortField.PLAY_COUNT)), ["A1", "B1", "B2"])

    def test_most_played_first(self):
        tracks = [track("Pouco", play_count=1), track("Muito", play_count=9), track("Nunca")]
        self.assertEqual(
            self.titles(library.sort_tracks(tracks, SortField.PLAY_COUNT, descending=True)), ["Muito", "Pouco", "Nunca"]
        )

    def test_never_played_last_when_sorting_by_last_played(self):
        tracks = [track("Nunca"), track("Ontem", last_played_at=datetime(2026, 11, 6)), track("Hoje", last_played_at=datetime(2026, 11, 7))]
        self.assertEqual(
            self.titles(library.sort_tracks(tracks, SortField.LAST_PLAYED, descending=True)), ["Hoje", "Ontem", "Nunca"]
        )

    def test_every_sort_field_is_supported(self):
        tracks = [track("A"), track("B", year=2000, track_no=1, last_played_at=DAY)]
        for field in SortField:
            with self.subTest(field):
                self.assertEqual(len(library.sort_tracks(tracks, field)), 2)

    def test_query_filters_then_sorts(self):
        tracks = [track("Rock 2", genre="Rock", year=2020), track("Rock 1", genre="Rock", year=2010), track("Pop", genre="Pop")]
        result = library.query_tracks(tracks, TrackQuery(genre="Rock", sort=SortField.YEAR))
        self.assertEqual(self.titles(result), ["Rock 1", "Rock 2"])


if __name__ == "__main__":
    unittest.main()
