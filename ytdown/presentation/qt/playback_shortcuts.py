"""Atalhos de reprodução da janela, sem interceptar edição de texto."""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QLineEdit,
                               QPlainTextEdit, QTextEdit, QWidget)


class PlaybackShortcuts(QObject):
    def __init__(self, window, playback):
        super().__init__(window)
        self.window = window
        self.playback = playback
        QApplication.instance().installEventFilter(self)

    def shutdown(self):
        QApplication.instance().removeEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.KeyPress or not isinstance(watched, QWidget):
            return False
        if watched.window() is not self.window or QApplication.activeModalWidget() is not None:
            return False
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
            return False
        if isinstance(focus, QComboBox) and focus.isEditable():
            return False
        key, modifiers = event.key(), event.modifiers()
        if modifiers == Qt.KeyboardModifier.NoModifier and key == Qt.Key.Key_Space:
            self.playback.play_pause()
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_Left:
            self.playback.previous()
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_Right:
            self.playback.next()
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_M:
            self.playback.set_muted(not self.playback.muted)
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_S:
            self.playback.set_shuffle(not self.playback.shuffle)
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_T:
            self.playback.cycle_repeat()
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            delta = 5 if key == Qt.Key.Key_Up else -5
            self.playback.set_volume(max(0, min(100, self.playback.volume + delta)))
        else:
            return False
        return True
