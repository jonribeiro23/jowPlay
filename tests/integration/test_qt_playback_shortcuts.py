"""Atalhos locais em uma janela Qt offscreen."""

import unittest
from unittest.mock import Mock

from tests.qt_support import dispose, qt_app
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit, QTextEdit, QVBoxLayout, QWidget

from ytdown.presentation.qt.playback_shortcuts import PlaybackShortcuts


class ShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        self.window = QWidget()
        layout = QVBoxLayout(self.window)
        self.edit = QLineEdit()
        self.multiline = QTextEdit()
        layout.addWidget(self.edit)
        layout.addWidget(self.multiline)
        self.playback = Mock(volume=98, muted=False, shuffle=False)
        self.shortcuts = PlaybackShortcuts(self.window, self.playback)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        self.addCleanup(dispose, self.window)

    def test_commands_and_volume_bounds(self):
        self.window.setFocus()
        for key, method in ((Qt.Key.Key_Space, 'play_pause'), (Qt.Key.Key_Left, 'previous'),
                            (Qt.Key.Key_Right, 'next')):
            modifiers = Qt.KeyboardModifier.NoModifier if key == Qt.Key.Key_Space else Qt.KeyboardModifier.ControlModifier
            QTest.keyClick(self.window, key, modifiers)
            getattr(self.playback, method).assert_called_once_with()
        QTest.keyClick(self.window, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
        self.playback.set_volume.assert_called_with(100)
        self.playback.volume = 2
        QTest.keyClick(self.window, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
        self.playback.set_volume.assert_called_with(0)

    def test_mute_shuffle_and_repeat_use_current_state(self):
        self.window.setFocus()
        control = Qt.KeyboardModifier.ControlModifier
        for key in (Qt.Key.Key_M, Qt.Key.Key_S, Qt.Key.Key_T):
            QTest.keyClick(self.window, key, control)
        self.playback.set_muted.assert_called_once_with(True)
        self.playback.set_shuffle.assert_called_once_with(True)
        self.playback.cycle_repeat.assert_called_once_with()
        self.playback.muted = self.playback.shuffle = True
        QTest.keyClick(self.window, Qt.Key.Key_M, control)
        QTest.keyClick(self.window, Qt.Key.Key_S, control)
        self.playback.set_muted.assert_called_with(False)
        self.playback.set_shuffle.assert_called_with(False)

    def test_editors_keep_keys_and_shutdown_removes_filter(self):
        for editor in (self.edit, self.multiline):
            editor.setFocus()
            QTest.keyClick(editor, Qt.Key.Key_Space)
            QTest.keyClick(editor, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
            for key in (Qt.Key.Key_M, Qt.Key.Key_S, Qt.Key.Key_T):
                QTest.keyClick(editor, key, Qt.KeyboardModifier.ControlModifier)
        self.playback.play_pause.assert_not_called()
        self.playback.previous.assert_not_called()
        self.playback.set_muted.assert_not_called()
        self.playback.set_shuffle.assert_not_called()
        self.playback.cycle_repeat.assert_not_called()
        self.assertEqual(self.edit.text(), ' ')
        self.shortcuts.shutdown()
        self.window.setFocus()
        QTest.keyClick(self.window, Qt.Key.Key_Space)
        self.playback.play_pause.assert_not_called()
