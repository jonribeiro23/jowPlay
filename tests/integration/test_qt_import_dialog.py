"""Import dialog lifecycle and composition through the real bootstrap."""
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.qt_support import qt_app, dispose, wait_until
from tests.integration import test_import_audios as import_tests
from tests.fakes import FakeAudioPlayer, FakeDownloader, FakeCovers, FakeTags
from ytdown.application.extraction import ExtractAudio, ExtractBatch
from ytdown.application.importing import ImportResult
from ytdown.application.playback import Playback
from ytdown.bootstrap import build_main_window
from ytdown.presentation.qt.import_dialog import ImportDialog
from ytdown.presentation.qt.pages import PageId
from ytdown.presentation.qt.send_dialog import PhoneSharing


class ImportDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_worker_thread_cancel_reject_waits_and_summary(self):
        entered, release = threading.Event(), threading.Event()
        threads = []
        def job(folders, cancel, progress):
            threads.append(threading.get_ident())
            entered.set()
            release.wait(3)
            return ImportResult(imported=1, cancelled=cancel.is_set())
        dialog = ImportDialog(job)
        dialog.folders.addItem('old')
        dialog.start()
        self.assertTrue(entered.wait(2))
        dialog.reject()
        self.assertTrue(dialog.is_working())
        self.assertTrue(dialog.cancel_event.is_set())
        release.set()
        self.assertTrue(wait_until(lambda: not dialog.is_working()))
        self.assertNotEqual(threads[0], threading.get_ident())
        self.assertIn('Importadas: 1', dialog.status.text())
        dispose(dialog)

    def test_busy_prevents_start(self):
        dialog = ImportDialog(lambda *args: self.fail('must not run'), lambda: True)
        dialog.folders.addItem('old')
        dialog.start()
        self.assertFalse(dialog.is_working())
        dispose(dialog)

    def test_choose_multiple_folders(self):
        dialog = ImportDialog(lambda *args: None)
        with patch('ytdown.presentation.qt.import_dialog.QFileDialog.getExistingDirectory',
                   side_effect=['first', 'second', 'first', '']):
            for _ in range(4):
                dialog.choose_folder()
        self.assertEqual([dialog.folders.item(i).text() for i in range(dialog.folders.count())],
                         ['first', 'second'])
        dispose(dialog)


class ImportCompositionTests(unittest.TestCase):
    setUp = import_tests.ImportTests.setUp
    audio = import_tests.ImportTests.audio

    def test_window_close_waits_for_import_and_database_stays_open(self):
        self.app = qt_app()
        playback = Playback(FakeAudioPlayer(), self.library.storage, tracks=self.library.tracks)
        batch = ExtractBatch(ExtractAudio(FakeDownloader(), FakeCovers(), FakeTags()), FakeCovers())
        window = build_main_window(self.library, playback, batch, PhoneSharing(lambda _: None))
        self.addCleanup(dispose, window)
        window.show()
        window.import_requested.emit()
        dialog = window.background_dialogs[0]
        entered, release = threading.Event(), threading.Event()
        closed = []
        window.closing.connect(lambda: closed.append(True))
        def job(folders, cancel, progress):
            entered.set()
            release.wait(3)
            return ImportResult(cancelled=cancel.is_set())
        dialog.use_case = job
        dialog.folders.addItem('old')
        dialog.start()
        self.assertTrue(entered.wait(2))
        window.close()
        self.assertTrue(dialog.cancel_event.is_set())
        self.assertFalse(closed)
        self.assertEqual(self.library.tracks.list_tracks(), [])
        release.set()
        self.assertTrue(wait_until(lambda: bool(closed)))
        self.assertFalse(window.background_dialogs)
    # Reuse setup and audio factory, not the integration test methods.
    def test_window_import_refresh_and_shutdown(self):
        self.app = qt_app()
        self.audio()
        playback = Playback(FakeAudioPlayer(), self.library.storage, tracks=self.library.tracks)
        batch = ExtractBatch(ExtractAudio(FakeDownloader(), FakeCovers(), FakeTags()), FakeCovers())
        window = build_main_window(self.library, playback, batch, PhoneSharing(lambda _: None))
        self.addCleanup(dispose, window)
        window.show()
        self.assertEqual(window.import_button.text(), 'Importar \u00e1udios extra\u00eddos...')
        window.import_requested.emit()
        dialog = window.background_dialogs[0]
        dialog.folders.addItem(str(self.source))
        dialog.start()
        self.assertTrue(window.page(PageId.EXTRACT).external_busy())
        window.options_requested.emit()
        self.assertEqual(len(window.background_dialogs), 1)
        self.assertTrue(wait_until(lambda: not dialog.is_working()))
        self.assertEqual(window.page(PageId.SONGS).model.rowCount(), 1)
        dialog.reject()
