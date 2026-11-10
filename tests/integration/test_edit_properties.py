import tempfile
import unittest
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from ytdown.application.library import EditTrackProperties
from ytdown.domain.errors import LibraryError
from ytdown.domain.library import Track
from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
from ytdown.infrastructure.sqlite_library import SqliteTrackRepository


class Tags:
    def update(self, path, changes):
        path.write_bytes(path.read_bytes() + repr(changes).encode())


class EditPropertiesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.storage = FileSystemLibraryStorage(root / "music")
        self.storage.root.mkdir()
        self.repo = SqliteTrackRepository(root / "db.sqlite")
        self.track = self.repo.add(Track("old.mp3", "Old", datetime.now(), artist="Artist"))
        self.original = self.storage.absolute(self.track.rel_path)
        self.original.write_bytes(b"original")
        self.edit = EditTrackProperties(self.storage, self.repo, Tags())

    def tearDown(self):
        self.repo.close()
        self.temp.cleanup()

    def test_edit_moves_file_and_updates_index_without_overwriting(self):
        from ytdown.domain.library_paths import library_path
        collision = self.storage.absolute(library_path("New artist", "", "New", None, ".mp3", self.storage.max_relative_length()))
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_bytes(b"other")
        result = self.edit(self.track.id, {"title": "New", "artist": "New artist", "genre": "Rock"})
        self.assertEqual(self.repo.get(self.track.id), result)
        self.assertEqual(collision.read_bytes(), b"other")
        self.assertFalse(self.original.exists())
        self.assertTrue(self.storage.absolute(result.rel_path).read_bytes().startswith(b"original"))
        self.assertEqual(result.genre, "Rock")

    def test_database_failure_restores_original(self):
        with patch.object(self.repo, "update_if_unchanged", side_effect=RuntimeError("banco")):
            with self.assertRaises(LibraryError):
                self.edit(self.track.id, {"title": "New"})
        self.assertEqual(self.original.read_bytes(), b"original")
        self.assertEqual(self.repo.get(self.track.id), self.track)
        backups = list((self.storage.root / ".ytdown-recovery").rglob("original.mp3"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"original")

    def test_locked_original_keeps_file_and_index(self):
        original_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            if path == self.original:
                raise PermissionError("arquivo em uso")
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", autospec=True, side_effect=unlink):
            with self.assertRaisesRegex(LibraryError, "arquivo em uso"):
                self.edit(self.track.id, {"title": "New"})
        self.assertEqual(self.original.read_bytes(), b"original")
        self.assertEqual(self.repo.get(self.track.id), self.track)

    def test_concurrent_change_during_edit_is_not_overwritten(self):
        def concurrent(path, changes):
            self.repo.update(replace(self.track, genre="Atualizado", play_count=3))
            path.write_bytes(b"editado")
        with patch.object(self.edit.tags, "update", side_effect=concurrent):
            with self.assertRaisesRegex(LibraryError, "outra operação"):
                self.edit(self.track.id, {"title": "Novo"})
        self.assertEqual(self.repo.get(self.track.id).genre, "Atualizado")
        self.assertEqual(self.repo.get(self.track.id).play_count, 3)
        self.assertEqual(self.original.read_bytes(), b"original")

    def test_latest_track_is_used_and_untouched_fields_are_preserved(self):
        self.repo.update(replace(self.track, genre="Atualizado", play_count=2))
        result = self.edit(self.track.id, {"title": "Novo"})
        self.assertEqual((result.genre, result.play_count), ("Atualizado", 2))

    def test_real_mp3_cover_change_and_removal_preserve_other_tags(self):
        from mutagen.id3 import ID3, TIT2, TPE1
        from ytdown.infrastructure.covers import PillowCoverLoader
        from ytdown.infrastructure.resources import asset
        from ytdown.infrastructure.tags import MutagenTagWriter
        tags = ID3()
        tags.add(TIT2(encoding=3, text="Old"))
        tags.add(TPE1(encoding=3, text="Artist"))
        tags.save(self.original)
        self.edit.tags = MutagenTagWriter()
        cover = PillowCoverLoader(asset("default_cover.jpg")).load(None)
        updated = self.edit(self.track.id, {"cover": cover})
        path = self.storage.absolute(updated.rel_path)
        self.assertEqual(ID3(path).getall("APIC")[0].data, cover)
        self.assertEqual(str(ID3(path)["TPE1"]), "Artist")
        updated = self.edit(self.track.id, {"cover": None})
        self.assertFalse(ID3(self.storage.absolute(updated.rel_path)).getall("APIC"))

    @unittest.skipUnless(os.name == "nt", "bloqueio específico do Windows")
    def test_windows_handle_without_delete_sharing_preserves_original(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(self.original), 0x80000000, 1, None, 3, 0x80, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
        try:
            with self.assertRaises(LibraryError):
                self.edit(self.track.id, {"title": "Novo"})
            self.assertEqual(self.original.read_bytes(), b"original")
            self.assertEqual(self.repo.get(self.track.id), self.track)
        finally:
            kernel.CloseHandle(handle)

    def test_failed_tag_write_preserves_original(self):
        with patch.object(self.edit.tags, "update", side_effect=RuntimeError("tags")):
            with self.assertRaises(LibraryError):
                self.edit(self.track.id, {"title": "New"})
        self.assertEqual(self.original.read_bytes(), b"original")
        self.assertEqual(self.repo.get(self.track.id), self.track)
