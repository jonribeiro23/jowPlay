import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from ytdown.application.library import DeleteTracks
from ytdown.application.playlists import ManagePlaylists
from ytdown.domain.library import Track
from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
from ytdown.infrastructure.sqlite_library import MIGRATIONS, SqliteTrackRepository
from ytdown.infrastructure.sqlite_playlists import SqlitePlaylistRepository
from tests.fakes import FakeAudioPlayer
from ytdown.application.playback import Playback


class PlaylistIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'library.db'
        old = SqliteTrackRepository(self.path, migrations=MIGRATIONS[:1])
        self.a = old.add(Track('a.mp3', 'a', datetime.now(), duration_ms=10))
        self.b = old.add(Track('b.mp3', 'b', datetime.now(), duration_ms=20))
        old.close()
        self.tracks = SqliteTrackRepository(self.path)
        self.addCleanup(self.tracks.close)
        self.repo = SqlitePlaylistRepository(self.tracks)
        self.service = ManagePlaylists(self.repo)

    def test_migration_crud_queue_and_rollback(self):
        self.assertEqual(self.tracks.get(self.a.id), self.a)
        p = self.service.save_queue(' Straße ', [self.a, self.b, self.a])
        self.assertEqual(p.duration_ms, 40)
        with self.assertRaises(ValueError):
            self.service.create('STRASSE')
        with self.assertRaises(ValueError):
            self.service.add_tracks(p.id, [self.b.id, 999999])
        self.assertEqual(self.repo.get(p.id), p)
        p = self.service.move_track(p.id, 2, 1)
        p = self.service.remove_track(p.id, 0)
        p = self.service.rename(p.id, 'Outra')
        self.assertEqual([t.id for t in p.tracks], [self.a.id, self.b.id])
        self.assertEqual(self.repo.list_playlists(), [p])
        self.service.delete(p.id)
        self.assertIsNone(self.repo.get(p.id))

    def test_concurrent_connections_preserve_additions_and_unique_names(self):
        other = SqliteTrackRepository(self.path)
        self.addCleanup(other.close)
        repos = [self.repo, SqlitePlaylistRepository(other)]
        p = self.repo.create('Teste')
        def add(i):
            repos[i % 2].add_tracks(p.id, [self.a.id])
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(add, range(40)))
        self.assertEqual(len(self.repo.get(p.id).tracks), 40)
        def create(i):
            try:
                repos[i % 2].create('ÚNICA' if i % 2 else 'única')
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(create, range(12))), 1)

    def test_delete_tracks_cascades_and_failure_rolls_back(self):
        root = Path(self.temp.name) / 'files'
        root.mkdir()
        (root / 'a.mp3').write_bytes(b'a')
        (root / 'b.mp3').write_bytes(b'b')
        storage = FileSystemLibraryStorage(root, lambda path: path.unlink())
        playback = Playback(FakeAudioPlayer(), storage, tracks=self.tracks)
        delete = DeleteTracks(storage, self.tracks, playback)
        p = self.service.save_queue('fila', [self.a, self.b, self.a])
        with self.assertRaises(OSError):
            self.tracks.remove_with_file(self.a.id, lambda: (_ for _ in ()).throw(OSError('falha')))
        self.assertEqual(len(self.repo.get(p.id).tracks), 3)
        removed, errors = delete([self.a.id])
        self.assertEqual((removed, errors), ({self.a.id}, []))
        self.assertEqual([t.id for t in self.repo.get(p.id).tracks], [self.b.id])
