"""A integridade usa a pasta real, sem confundir raiz ausente com milhares de arquivos apagados."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from ytdown.application.library import CheckLibrary, RemoveUnavailableTracks
from ytdown.bootstrap import build_library
from ytdown.domain.library import Track


class CheckLibraryIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.library = build_library(self.root / "library.db", self.root / "settings.json", self.root / "music")
        self.addCleanup(self.library.close)
        self.music = self.library.storage.root
        self.music.mkdir()
        self.track = self.library.tracks.add(Track("Artist/song.mp3", "Song", datetime.now()))
        self.file = self.library.storage.absolute(self.track.rel_path)
        self.file.parent.mkdir()
        self.file.write_bytes(b"audio")

    def test_delete_restore_and_root_unavailable(self):
        check = CheckLibrary(self.library.storage, self.library.tracks)
        self.assertEqual(check().changed, 0)
        self.file.unlink()
        self.assertEqual(check().changed, 1)
        self.assertTrue(self.library.tracks.get(self.track.id).missing)
        self.file.write_bytes(b"audio")
        self.assertEqual(check().changed, 1)
        self.assertFalse(self.library.tracks.get(self.track.id).missing)

        unavailable = self.root / "music-offline"
        self.music.rename(unavailable)
        result = check()
        self.assertFalse(result.root_available)
        self.assertEqual(result.changed, 0)
        self.assertFalse(self.library.tracks.get(self.track.id).missing)

    def test_remove_unavailable_only_removes_the_index_entry(self):
        self.file.unlink()
        CheckLibrary(self.library.storage, self.library.tracks)()
        self.assertEqual(RemoveUnavailableTracks(self.library.storage, self.library.tracks)(), {self.track.id})
        self.assertIsNone(self.library.tracks.get(self.track.id))
        self.assertFalse(self.file.exists())


if __name__ == "__main__":
    unittest.main()
