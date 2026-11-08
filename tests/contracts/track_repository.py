"""Contrato do TrackRepository: o que qualquer implementação precisa cumprir.

Uso: uma classe de teste herda de `TrackRepositoryContract` e de `unittest.TestCase`
e implementa `make_repository()`. As consultas são comparadas com as funções de
referência do domínio, então uma implementação em SQL não pode divergir delas.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ytdown.domain import library
from ytdown.domain.library import SortField, Track, TrackQuery


def sample_tracks() -> list[Track]:
    """Biblioteca pequena que cobre os casos difíceis: acentos, campos vazios,
    álbuns de mesmo nome com artistas diferentes, faixa indisponível, empates.
    """

    def track(path, title, **fields):
        return Track(rel_path=path, title=title, added_at=fields.pop("added_at", datetime(2026, 11, 1)), **fields)

    return [
        track("Ana/Sol/01.mp3", "Manhã", artist="Ana", album="Sol", genre="MPB", year=2020, track_no=1,
              duration_ms=200_000, source_url="https://youtu.be/a1", play_count=3,
              last_played_at=datetime(2026, 11, 5)),
        track("Ana/Sol/02.mp3", "Ação", artist="Ana", album="Sol", genre="MPB", year=2020, track_no=2,
              duration_ms=180_000, source_url="https://youtu.be/a2"),
        track("Ana/Sol/sem-numero.mp3", "Bônus", artist="Ana", album="Sol", genre="MPB", duration_ms=60_000),
        track("Bia/Sol/01.mp3", "Lua", artist="Bia", album="Sol", genre="Rock", year=2018, track_no=1,
              duration_ms=240_000, play_count=10, added_at=datetime(2026, 11, 3)),
        track("Álvaro/Álbum/01.mp3", "Estrela", artist="Álvaro", album="Álbum", genre="rock", year=2021,
              track_no=1, duration_ms=150_000, missing=True),
        track("Desconhecido/01.mp3", "Sem dados", duration_ms=90_000, added_at=datetime(2026, 11, 6)),
    ]


class TrackRepositoryContract:
    def make_repository(self):  # pragma: no cover - implementado por quem herda
        raise NotImplementedError

    def setUp(self):
        super().setUp()
        self.repo = self.make_repository()
        self.saved = [self.repo.add(t) for t in sample_tracks()]

    # --- gravação

    def test_add_assigns_distinct_ids(self):
        ids = [t.id for t in self.saved]
        self.assertTrue(all(isinstance(i, int) for i in ids))
        self.assertEqual(len(set(ids)), len(ids))

    def test_two_tracks_cannot_share_a_path(self):
        with self.assertRaises(ValueError):
            self.repo.add(replace(sample_tracks()[0], title="Outra"))

    def test_get_returns_exactly_what_was_saved(self):
        for track in self.saved:
            self.assertEqual(self.repo.get(track.id), track)

    def test_update_replaces_every_field(self):
        changed = replace(self.saved[0], title="Novo título", album="", year=None, play_count=4,
                          last_played_at=datetime(2026, 11, 7, 10, 30), missing=True)
        self.repo.update(changed)
        self.assertEqual(self.repo.get(changed.id), changed)

    def test_update_of_unknown_track_fails(self):
        with self.assertRaises(KeyError):
            self.repo.update(replace(self.saved[0], id=999_999))

    def test_remove(self):
        self.repo.remove(self.saved[0].id)
        self.assertIsNone(self.repo.get(self.saved[0].id))
        self.repo.remove(self.saved[0].id)  # Remover de novo não falha.

    def test_find_by_source_url_and_path(self):
        self.assertEqual(self.repo.find_by_source_url("https://youtu.be/a2"), self.saved[1])
        self.assertIsNone(self.repo.find_by_source_url("https://youtu.be/nao-existe"))
        self.assertEqual(self.repo.find_by_path("Bia/Sol/01.mp3"), self.saved[3])
        self.assertIsNone(self.repo.find_by_path("nao/existe.mp3"))

    # --- consultas: precisam bater com as funções de referência do domínio

    def assert_query(self, query: TrackQuery):
        self.assertEqual(self.repo.list_tracks(query), library.query_tracks(self.saved, query), query)

    def test_list_everything_in_natural_order(self):
        self.assert_query(TrackQuery())

    def test_text_search_ignores_accents_and_case(self):
        for text in ("acao", "AÇÃO", "sol ana", "rock", "inexistente"):
            self.assert_query(TrackQuery(text=text))

    def test_filters_by_display_names(self):
        for query in (
            TrackQuery(artist="Ana"),
            TrackQuery(album="Sol"),
            TrackQuery(genre="Rock"),
            TrackQuery(artist=library.UNKNOWN_ARTIST),
            TrackQuery(album=library.UNKNOWN_ALBUM, genre=library.UNKNOWN_GENRE),
            TrackQuery(include_missing=False),
        ):
            self.assert_query(query)

    def test_every_sort_field_in_both_directions(self):
        for field in SortField:
            for descending in (False, True):
                self.assert_query(TrackQuery(sort=field, descending=descending))

    def test_summaries(self):
        self.assertEqual(self.repo.artists(), library.summarize_artists(self.saved))
        self.assertEqual(self.repo.albums(), library.summarize_albums(self.saved))
        self.assertEqual(self.repo.albums(artist="Ana"), library.summarize_albums(self.saved[:3]))
        self.assertEqual(self.repo.genres(), library.summarize_genres(self.saved))
