"""Interações da fila com Playback em Qt offscreen."""
import unittest
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtTest import QTest

from tests.fakes import FakeAudioPlayer, FakeLibraryStorage, InMemoryTrackRepository
from tests.qt_support import dispose, qt_app
from ytdown.application.playback import Playback
from ytdown.domain.library import Track
from ytdown.infrastructure.json_settings import JsonSettings
from ytdown.presentation.qt.play_queue_pane import PlayQueuePane
from ytdown.presentation.qt.songs_page import SongsPage, TRACKS_MIME


class Drop:
    def __init__(self, source, position, tracks=False):
        self._source, self._position = source, QPointF(position)
        self._mime = QMimeData()
        if tracks:
            self._mime.setData(TRACKS_MIME, b"tracks")
        self.accepted = False

    def source(self): return self._source
    def position(self): return self._position
    def mimeData(self): return self._mime
    def setDropAction(self, action): self.action = action
    def accept(self): self.accepted = True
    def ignore(self): self.accepted = False


class QueuePaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        self.playback = Playback(FakeAudioPlayer(), FakeLibraryStorage())
        self.pane = PlayQueuePane()
        self.pane.bind(self.playback)
        self.pane.show()
        self.addCleanup(dispose, self.pane)
        self.a = Track('a.mp3', 'A', datetime.now(), duration_ms=61000)
        self.b = Track('b.mp3', 'B', datetime.now(), duration_ms=2000)

    def test_external_changes_duplicate_positions_and_commands(self):
        self.playback.play_tracks([self.a, self.b, self.a], 2)
        self.assertEqual(self.pane.items.count(), 3)
        self.assertEqual(self.pane.total.text(), '3 faixas · 2:04')
        self.assertTrue(self.pane.items.item(2).font().bold())
        self.assertFalse(self.pane.items.item(0).font().bold())
        self.assertFalse(self.pane.save_button.isEnabled())
        self.pane.items.itemDoubleClicked.emit(self.pane.items.item(0))
        self.assertEqual(self.playback.current_index, 0)
        self.playback.set_shuffle(True)
        self.pane.items.setCurrentRow(2)
        QTest.keyClick(self.pane.items, Qt.Key.Key_Delete)
        self.assertEqual(self.playback.queue, [self.a, self.b])
        self.assertEqual(self.playback.current_index, 0)
        self.pane.clear_button.click()
        self.assertEqual(self.playback.queue, [])
        self.assertFalse(self.pane.clear_button.isEnabled())

    def test_internal_drop_and_external_append(self):
        self.playback.play_tracks([self.a, self.b, self.a], 2)
        self.playback.set_shuffle(True)
        self.pane.items.setCurrentRow(2)
        point = self.pane.items.visualItemRect(self.pane.items.item(0)).topLeft()
        drop = Drop(self.pane.items, point)
        self.pane.items.dropEvent(drop)
        self.assertTrue(drop.accepted)
        self.assertEqual(self.playback.queue, [self.a, self.a, self.b])
        self.assertEqual(self.playback.current_index, 0)
        self.assertEqual(self.pane.items.currentRow(), 0)
        self.playback.move(0, 2)
        self.assertEqual(self.pane.items.currentRow(), 2)
        self.assertTrue(self.pane.items.item(2).isSelected())
        self.assertEqual(self.playback.current_index, 2)
        repo = InMemoryTrackRepository()
        repo.add(self.a)
        repo.add(self.b)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        page = SongsPage(repo, self.playback, JsonSettings(Path(temp.name) / 'settings.json'))
        self.addCleanup(dispose, page)
        page.table.selectAll()
        drop = Drop(page.table, point, tracks=True)
        self.pane.items.dropEvent(drop)
        self.assertTrue(drop.accepted)
        self.assertEqual(self.playback.queue[3:], page.model.tracks)

    def test_shutdown_disconnects_listener(self):
        listener = self.pane._listener
        self.pane.shutdown()
        self.assertNotIn(listener, self.playback._listeners)
        self.playback.append([self.a])
        self.assertEqual(self.pane.items.count(), 0)
