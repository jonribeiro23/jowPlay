"""Janela "Opções": mudar a pasta da biblioteca, com o caso de uso real sobre pastas temporárias."""

import tempfile
import threading
import unittest
from pathlib import Path

from tests.fakes import InMemoryTrackRepository
from tests.qt_support import dispose, qt_app, wait_until
from ytdown.application.library import ChangeLibraryFolder
from ytdown.domain.errors import LibraryError
from ytdown.infrastructure.json_settings import JsonSettings
from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
from ytdown.presentation import texts
from ytdown.presentation.qt.options_dialog import OptionsDialog


class OptionsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.old_root, self.new_root = self.base / "Antiga", self.base / "Nova"
        (self.old_root / "Artista" / "Álbum").mkdir(parents=True)
        (self.old_root / "Artista" / "Álbum" / "faixa.mp3").write_bytes(b"audio")
        self.storage = FileSystemLibraryStorage(self.old_root)
        self.settings = JsonSettings(self.base / "settings.json")
        self.change = ChangeLibraryFolder(self.storage, InMemoryTrackRepository(), self.settings)
        self.busy = False
        self.chosen = self.new_root

    def open_dialog(self, change=None):
        dialog = OptionsDialog(lambda: self.storage.root, change or self.change, lambda: self.busy,
                               choose_folder=lambda parent, current: self.chosen)
        dialog.show()
        self.addCleanup(dispose, dialog)
        self.addCleanup(lambda: wait_until(lambda: not dialog.is_moving(), 5000))
        return dialog

    def test_shows_the_current_folder(self):
        self.assertEqual(self.open_dialog().folder.text(), str(self.old_root))

    def test_changing_moves_the_library_and_saves_the_choice(self):
        dialog = self.open_dialog()
        dialog.change_button.click()
        self.assertTrue(wait_until(lambda: not dialog.is_moving(), 5000))
        self.assertTrue((self.new_root / "Artista" / "Álbum" / "faixa.mp3").exists())
        self.assertEqual(dialog.folder.text(), str(self.new_root))
        self.assertEqual(self.settings.get("library_folder"), str(self.new_root))
        self.assertEqual(dialog.status.text(), texts.LIBRARY_MOVED.text)

    def test_cannot_change_during_an_extraction(self):
        self.busy = True
        dialog = self.open_dialog()
        dialog.change_button.click()
        self.assertFalse(dialog.is_moving())
        self.assertEqual(dialog.status.text(), texts.WAIT_FOR_EXTRACTION.text)
        self.assertTrue((self.old_root / "Artista" / "Álbum" / "faixa.mp3").exists())

    def test_giving_up_on_the_folder_choice_changes_nothing(self):
        self.chosen = None
        dialog = self.open_dialog()
        dialog.change_button.click()
        self.assertFalse(dialog.is_moving())
        self.assertEqual(dialog.folder.text(), str(self.old_root))

    def test_failure_is_explained_and_nothing_changes(self):
        def failing(new_root, on_progress):
            raise LibraryError("A nova pasta da biblioteca não pode ficar dentro da atual, nem conter a atual.")

        dialog = self.open_dialog(failing)
        dialog.change_button.click()
        self.assertTrue(wait_until(lambda: not dialog.is_moving(), 5000))
        self.assertIn("nada mudou", dialog.status.text())
        self.assertIn("dentro da atual", dialog.status.text())
        self.assertEqual(dialog.status.property("tone"), "error")
        self.assertEqual(dialog.folder.text(), str(self.old_root))

    def test_cannot_be_closed_while_moving(self):
        release = threading.Event()

        def slow(new_root, on_progress):
            on_progress(1, 3)
            release.wait(5)

        dialog = self.open_dialog(slow)
        dialog.change_button.click()
        self.assertTrue(wait_until(lambda: "1 de 3" in dialog.status.text(), 5000))
        self.assertFalse(dialog.close_button.isEnabled())
        dialog.close()
        dialog.reject()
        self.assertTrue(dialog.isVisible())
        release.set()
        self.assertTrue(wait_until(lambda: not dialog.is_moving(), 5000))
        self.assertTrue(dialog.close_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
