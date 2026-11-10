import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from tests.fakes import FakeAudioPlayer
from tests.qt_support import qt_app, dispose
from ytdown.application.library import DeleteTracks
from ytdown.application.playback import Playback
from ytdown.domain.library import Track
from ytdown.infrastructure.json_settings import JsonSettings
from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
from ytdown.infrastructure.sqlite_library import SqliteTrackRepository
from ytdown.presentation.qt.songs_page import SongsPage
from ytdown.presentation.qt.play_queue_pane import PlayQueuePane


class DeleteTracksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'library'
        self.trash = self.base / 'trash'
        self.trash.mkdir()
        self.storage = FileSystemLibraryStorage(self.root, self.fake_trash)
        self.repo = SqliteTrackRepository(self.base / 'library.db')
        self.addCleanup(self.repo.close)
        self.player = FakeAudioPlayer()
        self.playback = Playback(self.player, self.storage, tracks=self.repo)
        self.case = DeleteTracks(self.storage, self.repo, self.playback)
        self.tracks = []
        for name in ('a', 'b', 'c'):
            path = self.root / 'artist' / 'album' / (name + '.mp3')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
            self.tracks.append(self.repo.add(Track(path.relative_to(self.root).as_posix(), name, datetime.now())))

    def fake_trash(self, path):
        path.rename(self.trash / path.name)

    def test_current_duplicates_and_empty_directories(self):
        a, b, c = self.tracks
        self.playback.play_tracks([a, a, b, c])
        removed, errors = self.case([a.id, a.id, c.id])
        self.assertEqual(removed, {a.id, c.id})
        self.assertFalse(errors)
        self.assertEqual(self.playback.queue, [b])
        self.assertEqual(self.playback.current.id, b.id)
        self.assertEqual(self.player.path, self.storage.absolute(b.rel_path))
        self.assertEqual((self.trash / 'a.mp3').read_bytes(), b'a')
        self.case([b.id])
        self.assertTrue(self.root.exists())
        self.assertFalse((self.root / 'artist').exists())

    def test_partial_failure_and_database_failure_restore_file(self):
        a, b, c = self.tracks
        def trash(path):
            if path.name == 'b.mp3':
                raise OSError('em uso')
            self.fake_trash(path)
        self.storage._trash_file = trash
        removed, errors = self.case([a.id, b.id])
        self.assertEqual(removed, {a.id})
        self.assertEqual(len(errors), 1)
        self.assertIsNotNone(self.repo.get(b.id))
        self.assertTrue(self.storage.exists(b.rel_path))
        original = self.repo.remove_with_file
        def fail_after_file(track_id, callback):
            def fail():
                callback()
                raise OSError('banco')
            original(track_id, fail)
        with patch.object(self.repo, 'remove_with_file', fail_after_file):
            removed, errors = self.case([c.id])
        self.assertFalse(removed)
        self.assertTrue(errors)
        self.assertIsNotNone(self.repo.get(c.id))
        self.assertEqual(self.storage.absolute(c.rel_path).read_bytes(), b'c')

    def test_failed_current_keeps_duplicates_and_playback_advances(self):
        a, b, _ = self.tracks
        self.playback.play_tracks([a, a, b])
        def fail(path):
            raise OSError('em uso')
        self.storage._trash_file = fail
        removed, errors = self.case([a.id])
        self.assertFalse(removed)
        self.assertTrue(errors)
        self.assertEqual(self.playback.current.id, b.id)
        self.assertEqual([t.id for t in self.playback.queue].count(a.id), 2)
        self.assertTrue(self.storage.exists(a.rel_path))

    def test_ui_cancel_and_confirm_via_delete_key_and_menu(self):
        page = SongsPage(self.repo, self.playback, JsonSettings(self.base / 'settings.json'))
        self.addCleanup(dispose, page)
        page.track_actions.delete_tracks = self.case
        page.track_actions.refresh_library = page.refresh
        page.show()
        page.activateWindow()
        page.table.setFocus()
        self.app.processEvents()
        page.table.selectRow(0)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No) as question:
            QTest.keyClick(page.table, Qt.Key.Key_Delete)
        self.assertIn('1 faixa', question.call_args.args[2])
        self.assertEqual(len(self.repo.list_tracks()), 3)
        menu = page.track_actions.make_menu()
        action = next(a for a in menu.actions() if a.text() == 'Excluir da biblioteca')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            action.trigger()
        self.assertEqual(len(self.repo.list_tracks()), 2)

    def test_queue_delete_confirms_unique_tracks(self):
        a, b, _ = self.tracks
        self.playback.play_tracks([a, a, b])
        pane = PlayQueuePane()
        self.addCleanup(dispose, pane)
        pane.bind(self.playback)
        pane.delete_tracks = self.case
        pane.show()
        pane.activateWindow()
        pane.items.setFocus()
        self.app.processEvents()
        pane.items.item(0).setSelected(True)
        pane.items.item(1).setSelected(True)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes) as question:
            QTest.keyClick(pane.items, Qt.Key.Key_Delete)
        self.assertIn('1 faixa', question.call_args.args[2])
        self.assertEqual([track.id for track in self.playback.queue], [b.id])
        pane.shutdown()
