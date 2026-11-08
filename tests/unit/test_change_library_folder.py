import unittest
from dataclasses import replace
from pathlib import Path

from tests.contracts.track_repository import sample_tracks
from tests.fakes import InMemoryTrackRepository
from ytdown.application.library import LIBRARY_FOLDER_KEY, ChangeLibraryFolder, library_folder
from ytdown.domain.errors import LibraryError


class DictSettings(dict):
    def set(self, key, value):
        self[key] = value


class FakeStorage:
    def __init__(self, renamed=None, error=None):
        self.renamed = renamed or {}
        self.error = error
        self.relocated_to = None

    def relocate(self, new_root, on_progress):
        if self.error:
            raise self.error
        on_progress(1, 1)
        self.relocated_to = new_root
        return self.renamed


class ChangeLibraryFolderTests(unittest.TestCase):
    def setUp(self):
        self.tracks = InMemoryTrackRepository()
        self.saved = [self.tracks.add(t) for t in sample_tracks()[:2]]
        self.settings = DictSettings()

    def test_moves_files_and_remembers_the_new_folder(self):
        storage = FakeStorage()
        progress = []
        ChangeLibraryFolder(storage, self.tracks, self.settings)(Path("D:/Música"), lambda *p: progress.append(p))
        self.assertEqual(storage.relocated_to, Path("D:/Música"))
        self.assertEqual(self.settings[LIBRARY_FOLDER_KEY], str(Path("D:/Música")))
        self.assertEqual(progress, [(1, 1)])

    def test_files_renamed_on_collision_are_updated_in_the_index(self):
        old = self.saved[0].rel_path
        storage = FakeStorage(renamed={old: "Ana/Sol/01 (1).mp3"})
        ChangeLibraryFolder(storage, self.tracks, self.settings)(Path("D:/Música"))
        self.assertEqual(self.tracks.get(self.saved[0].id), replace(self.saved[0], rel_path="Ana/Sol/01 (1).mp3"))
        self.assertEqual(self.tracks.get(self.saved[1].id), self.saved[1])

    def test_failure_changes_nothing(self):
        storage = FakeStorage(error=LibraryError("disco cheio"))
        with self.assertRaises(LibraryError):
            ChangeLibraryFolder(storage, self.tracks, self.settings)(Path("D:/Música"))
        self.assertNotIn(LIBRARY_FOLDER_KEY, self.settings)
        self.assertEqual([self.tracks.get(t.id) for t in self.saved], self.saved)


class LibraryFolderTests(unittest.TestCase):
    def test_default_until_the_user_chooses(self):
        settings = DictSettings()
        self.assertEqual(library_folder(settings, Path("C:/Música/ytDown")), Path("C:/Música/ytDown"))
        settings.set(LIBRARY_FOLDER_KEY, "D:/Minhas músicas")
        self.assertEqual(library_folder(settings, Path("C:/Música/ytDown")), Path("D:/Minhas músicas"))


if __name__ == "__main__":
    unittest.main()
