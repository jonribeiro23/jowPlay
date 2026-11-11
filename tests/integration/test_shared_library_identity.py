import tempfile
import unittest
from contextlib import ExitStack, closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from ytdown.application.sharing import SharingSession
from ytdown.domain.library import Track
from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
from ytdown.infrastructure.sharing.device_store import JsonDeviceStore
from ytdown.infrastructure.sharing.library_resolver import LibraryShareResolver
from ytdown.infrastructure.sqlite_library import SqliteTrackRepository


class SharedLibraryIdentityTests(unittest.TestCase):
    def test_catalog_tracks_library_without_explicit_share_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storage = FileSystemLibraryStorage(root)
            devices = JsonDeviceStore(root / "pairing.json")
            tracks = SqliteTrackRepository(root / "library.db")
            try:
                path = root / "song.mp3"
                path.write_bytes(b"audio")
                track = tracks.add(Track(path.name, "Song", datetime.now()))
                session = SharingSession(devices, library=LibraryShareResolver(tracks, storage, devices))
                first = session.available()[0][0]
                restarted = SharingSession(devices, library=LibraryShareResolver(tracks, storage, devices))
                self.assertEqual(restarted.available()[0][0].id, first.id)
                moved = root / "renamed.mp3"
                path.rename(moved)
                tracks.update(replace(track, rel_path=moved.name))
                self.assertEqual(restarted.get(first.id).path, moved)
                tracks.remove(track.id)
                self.assertEqual(restarted.available(), [])
                self.assertIsNone(restarted.get(first.id))
            finally:
                tracks.close()

    def test_file_shared_before_registration_is_promoted_without_changing_id(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp)
            storage = FileSystemLibraryStorage(root)
            tracks = stack.enter_context(closing(SqliteTrackRepository(root / "library.db")))
            devices = JsonDeviceStore(root / "pairing.json")
            session = SharingSession(devices, library=LibraryShareResolver(tracks, storage, devices))
            path = root / "extracted.mp3"
            path.write_bytes(b"audio")
            first = session.share(path)
            track = tracks.add(Track("extracted.mp3", "Song", datetime.now()))
            self.assertEqual(session.share(path).id, first.id)
            moved = root / "renamed.mp3"
            path.rename(moved)
            tracks.update(replace(track, rel_path=moved.name))
            self.assertEqual(session.get(first.id).path, moved)
            self.assertEqual(len(session.available()), 1)

    def test_move_restart_reuse_and_fallback(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp)
            storage = FileSystemLibraryStorage(root / "music")
            storage.root.mkdir()
            db = root / "library.db"
            pairing = root / "pairing.json"
            devices = JsonDeviceStore(pairing)
            tracks = stack.enter_context(closing(SqliteTrackRepository(db)))
            path = storage.root / "old.mp3"
            path.write_bytes(b"audio")
            track = tracks.add(Track("old.mp3", "Song", datetime.now()))
            # Uma instalação atualizada preserva o ID já visto por clientes antigos.
            legacy_id = devices.shared_id(path)
            session = SharingSession(devices, library=LibraryShareResolver(tracks, storage, devices))
            shared = session.share(path)
            self.assertEqual(shared.id, legacy_id)
            moved = storage.root / "new.mp3"
            path.rename(moved)
            tracks.update(replace(track, rel_path="new.mp3"))
            self.assertEqual(session.get(shared.id).path, moved)
            self.assertEqual(session.share(moved).id, shared.id)
            self.assertEqual(len(session.available()), 1)
            tracks.close()
            tracks = stack.enter_context(closing(SqliteTrackRepository(db)))
            session = SharingSession(devices, library=LibraryShareResolver(tracks, storage, devices))
            self.assertEqual(session.share(moved).id, shared.id)
            other = SharingSession(JsonDeviceStore(pairing), library=LibraryShareResolver(tracks, storage, JsonDeviceStore(pairing)))
            self.assertEqual(other.share(moved).id, shared.id)
            storage.relocate(root / "relocated", lambda *_: None)
            moved = storage.root / "new.mp3"
            path = storage.root / "old.mp3"
            self.assertEqual(session.get(shared.id).path, moved)
            tracks.remove(track.id)
            self.assertIsNone(session.get(shared.id))
            moved.rename(path)
            replacement = tracks.add(Track("old.mp3", "Another", datetime.now()))
            self.assertEqual(replacement.id, track.id)  # SQLite pode reutilizar o último ROWID.
            replacement_id = other.share(path).id
            self.assertNotEqual(replacement_id, shared.id)
            self.assertIsNone(session.get(shared.id))
            external = root / "external.mp3"
            external.write_bytes(b"external")
            first = other.share(external).id
            again = SharingSession(JsonDeviceStore(pairing), library=LibraryShareResolver(tracks, storage, JsonDeviceStore(pairing)))
            self.assertEqual(again.share(external).id, first)
