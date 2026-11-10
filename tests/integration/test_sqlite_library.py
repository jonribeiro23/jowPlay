"""SqliteTrackRepository com bancos reais em pasta temporária."""

import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from tests.contracts.track_repository import TrackRepositoryContract, sample_tracks
from ytdown.domain.errors import LibraryError
from ytdown.domain.library import SortField, Track, TrackQuery
from ytdown.infrastructure.sqlite_library import MIGRATIONS, SqliteTrackRepository


class TempDatabase:
    """Pasta temporária com o banco; fecha as conexões antes de apagar (exigência do Windows)."""

    def setUp(self):
        # O caminho vem antes do super().setUp(): o contrato abre o repositório no seu setUp.
        temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        self.db_path = Path(temp.name) / "pasta nova" / "library.db"
        super().setUp()

    def open(self, **kwargs) -> SqliteTrackRepository:
        repo = SqliteTrackRepository(self.db_path, **kwargs)
        self.addCleanup(repo.close)
        return repo


class SqliteContractTests(TempDatabase, TrackRepositoryContract, unittest.TestCase):
    def make_repository(self):
        return self.open()


class SqliteTrackRepositoryTests(TempDatabase, unittest.TestCase):
    def test_record_play_preserves_edits_and_persists(self):
        repo = self.open()
        saved = repo.add(sample_tracks()[0])
        repo.update(replace(saved, title="Editada"))
        played = datetime(2026, 11, 9, 10, 30)
        updated = repo.record_play(saved.id, played)
        self.assertEqual((updated.title, updated.play_count, updated.last_played_at),
                         ("Editada", saved.play_count + 1, played))
        self.assertEqual(self.open().get(saved.id), updated)
        self.assertIsNone(repo.record_play(99999, played))

    def test_can_be_used_from_other_threads(self):
        # A extração registra faixas fora da thread da interface, que continua consultando.
        repo = self.open()
        tracks = sample_tracks()
        errors = []

        def add_some(part):
            try:
                for track in part:
                    repo.add(track)
                    repo.list_tracks()
            except Exception as exc:  # noqa: BLE001 - o teste mostra qualquer erro.
                errors.append(exc)

        workers = [threading.Thread(target=add_some, args=(tracks[i::3],)) for i in range(3)]
        for worker in workers:
            worker.start()
        for _ in range(20):
            repo.artists()
        for worker in workers:
            worker.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(len(repo.list_tracks(TrackQuery(include_missing=True))), len(tracks))

    def test_data_survives_reopening(self):
        first = self.open()
        saved = [first.add(t) for t in sample_tracks()]
        first.close()
        reopened = self.open()
        self.assertEqual([reopened.get(t.id) for t in saved], saved)
        self.assertEqual(len(reopened.list_tracks()), len(saved))

    def test_search_follows_renamed_tracks(self):
        # As colunas derivadas (busca, nomes de exibição) acompanham a alteração.
        repo = self.open()
        track = repo.add(sample_tracks()[0])
        repo.update(replace(track, title="Pôr do sol", artist=""))
        self.assertEqual(repo.list_tracks(TrackQuery(text="por do sol")), [repo.get(track.id)])
        self.assertEqual(repo.list_tracks(TrackQuery(text="manha")), [])
        self.assertEqual(repo.artists()[0].name, "Artista desconhecido")

    def test_new_database_is_at_the_latest_version(self):
        self.assertEqual(self.open().schema_version, MIGRATIONS[-1][0])

    def test_missing_migrations_are_applied_without_losing_data(self):
        old = self.open()
        saved = old.add(sample_tracks()[0])
        old.close()
        version_2 = (2, "ALTER TABLE tracks ADD COLUMN rating INTEGER NOT NULL DEFAULT 0")
        upgraded = self.open(migrations=[*MIGRATIONS, version_2])
        self.assertEqual(upgraded.schema_version, 2)
        self.assertEqual(upgraded.get(saved.id), saved)
        upgraded.close()
        with closing(sqlite3.connect(self.db_path)) as db:
            columns = [row[1] for row in db.execute("PRAGMA table_info(tracks)")]
        self.assertIn("rating", columns)

    def test_a_failing_migration_changes_nothing(self):
        old = self.open()
        saved = old.add(sample_tracks()[0])
        old.close()
        broken = (2, "ALTER TABLE tracks ADD COLUMN rating INTEGER; ISTO NAO E SQL")
        with self.assertRaises(LibraryError):
            self.open(migrations=[*MIGRATIONS, broken])
        reopened = self.open()
        self.assertEqual((reopened.schema_version, reopened.get(saved.id)), (1, saved))

    def test_database_from_a_newer_app_is_refused(self):
        self.open().close()
        with self.assertRaisesRegex(LibraryError, "versão mais nova"):
            self.open(migrations=[])
        self.db_path.rename(self.db_path.with_name("movido.db"))  # O arquivo não ficou preso (Windows).

    def test_unreadable_file_gives_a_clear_error(self):
        self.db_path.parent.mkdir(parents=True)
        self.db_path.write_bytes(b"isto nao e um banco sqlite" * 100)
        with self.assertRaisesRegex(LibraryError, "Não foi possível abrir a biblioteca"):
            self.open()


class PerformanceTests(TempDatabase, unittest.TestCase):
    """Critério da JOW-14: consultas em 5.000 faixas abaixo de 100 ms."""

    TRACKS = 5000
    LIMIT_MS = 100

    @classmethod
    def build_tracks(cls) -> list[Track]:
        start = datetime(2026, 1, 1)
        genres = ["MPB", "Rock", "Samba", "Forró", "Jazz", ""]
        return [
            Track(
                rel_path=f"Artista {i % 300}/Álbum {i % 500}/{i:05d}.mp3",
                title=f"Canção número {i} {'ação' if i % 7 == 0 else 'paz'}",
                artist=f"Artista {i % 300}" if i % 50 else "",
                album=f"Álbum {i % 500}",
                genre=genres[i % len(genres)],
                year=1990 + i % 35 if i % 9 else None,
                track_no=i % 12 + 1,
                duration_ms=180_000 + i,
                source_url=f"https://www.youtube.com/watch?v={i:011d}",
                added_at=start + timedelta(minutes=i),
                play_count=i % 23,
                last_played_at=start + timedelta(days=i % 40) if i % 3 else None,
            )
            for i in range(cls.TRACKS)
        ]

    def best_of_three_ms(self, action) -> float:
        timings = []
        for _ in range(3):
            began = time.perf_counter()
            action()
            timings.append((time.perf_counter() - began) * 1000)
        return min(timings)

    def test_queries_on_5000_tracks(self):
        repo = self.open()
        for track in self.build_tracks():
            repo.add(track)
        queries = {
            "listar tudo": lambda: repo.list_tracks(),
            "busca 'acao'": lambda: repo.list_tracks(TrackQuery(text="acao")),
            "ordenar por título desc": lambda: repo.list_tracks(TrackQuery(sort=SortField.TITLE, descending=True)),
            "filtrar artista": lambda: repo.list_tracks(TrackQuery(artist="Artista 7")),
            "resumo de artistas": repo.artists,
            "resumo de álbuns": repo.albums,
            "resumo de gêneros": repo.genres,
            "buscar por URL": lambda: repo.find_by_source_url("https://www.youtube.com/watch?v=00000004321"),
        }
        timings = {name: self.best_of_three_ms(action) for name, action in queries.items()}
        print("\n  " + "\n  ".join(f"{name}: {ms:.1f} ms" for name, ms in timings.items()))
        slow = {name: round(ms, 1) for name, ms in timings.items() if ms >= self.LIMIT_MS}
        self.assertEqual(slow, {})
        self.assertEqual(len(repo.list_tracks(TrackQuery(text="acao"))), len(range(0, self.TRACKS, 7)))


if __name__ == "__main__":
    unittest.main()
