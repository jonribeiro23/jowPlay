"""Página e janela compacta sincronizadas com Playback."""
from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QObject, Qt, Signal, Slot, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QPushButton,
                               QVBoxLayout, QWidget)

from ytdown.application.ports import PlayerState
from ytdown.presentation.qt.transport_bar import _Listener, _latest


class CoverResult(QObject):
    ready = Signal(int, QImage)


def _load_covers(requests, stopped, result, read_cover):
    while not stopped.is_set():
        request = requests.get()
        if request is None or stopped.is_set():
            return
        generation, track = request
        image = QImage()
        try:
            data = read_cover(track)
            if data:
                image = QImage.fromData(data).scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation)
        except Exception:
            pass
        if not stopped.is_set():
            result.ready.emit(generation, image)


class NowPlayingPage(QWidget):
    compact_requested = Signal()

    def __init__(self, playback, read_cover, default_cover):
        super().__init__()
        self.setObjectName("nowPlayingPage")
        self.playback = playback
        self._generation = 0
        self._has_requested = False
        self._stopped = threading.Event()
        self._requests = queue.Queue(maxsize=1)
        self._result = CoverResult()
        self._result.ready.connect(self._cover_ready)
        self._default = default_cover.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)
        self.cover = QLabel()
        self.cover.setFixedSize(300, 300)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.artist = QLabel()
        self.album = QLabel()
        self.year = QLabel()
        for label in (self.title, self.artist, self.album, self.year):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
        self.upcoming = QListWidget()
        self.upcoming.setAccessibleName("Próximas faixas")
        self.compact_button = QPushButton("Modo compacto")
        self.compact_button.clicked.connect(self.compact_requested)
        layout = QVBoxLayout(self)
        layout.addWidget(self.cover)
        for label in (self.title, self.artist, self.album, self.year):
            layout.addWidget(label)
        layout.addWidget(self.compact_button)
        layout.addWidget(QLabel("Próximas faixas"))
        layout.addWidget(self.upcoming)
        self._listener = _Listener(self)
        playback.add_listener(self._listener)
        listener, stopped, requests = self._listener, self._stopped, self._requests
        def cleanup():
            playback.remove_listener(listener)
            stopped.set()
            _latest(requests, None)
        self._cleanup = cleanup
        self.destroyed.connect(cleanup)
        self._worker = threading.Thread(target=_load_covers, args=(requests, stopped, self._result, read_cover),
                                        daemon=True, name="now-playing-cover")
        self._worker.start()
        self.on_track_changed(playback.current)
        self.on_queue_changed()

    def shutdown(self, retry=None):
        self._generation += 1
        self._cleanup()
        if not self._has_requested or not self._worker.is_alive():
            return True
        if retry is not None:
            QTimer.singleShot(25, retry)
        return False

    def on_track_changed(self, track):
        self._generation += 1
        self.title.setText(track.title if track else "Nada tocando")
        self.artist.setText(track.display_artist if track else "")
        self.album.setText(track.display_album if track else "")
        self.year.setText(str(track.year) if track and track.year is not None else "")
        self.cover.setPixmap(self._default)
        if track:
            self._has_requested = True
            _latest(self._requests, (self._generation, track))
        self.on_queue_changed()

    @Slot(int, QImage)
    def _cover_ready(self, generation, image):
        if not self._stopped.is_set() and generation == self._generation:
            self.cover.setPixmap(QPixmap.fromImage(image) if not image.isNull() else self._default)

    def on_queue_changed(self):
        self.upcoming.clear()
        self.upcoming.addItems([f"{track.title} — {track.display_artist}" for track in self.playback.upcoming()])

    def on_state_changed(self, state): pass
    def on_position_changed(self, position, duration): pass
    def on_track_unavailable(self, track, message): pass
    def on_settings_changed(self): pass


class CompactPlayer(QDialog):
    POSITION_KEY = "playback.compact_position"

    def __init__(self, playback, page, settings, parent=None):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Em reprodução")
        self.playback, self.page, self.settings = playback, page, settings
        self.cover = QLabel()
        self.cover.setFixedSize(100, 100)
        self.title = QLabel()
        self.artist = QLabel()
        for label in (self.title, self.artist):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
        self.previous = QPushButton("⏮")
        self.play = QPushButton("▶")
        self.next = QPushButton("⏭")
        self.previous.clicked.connect(playback.previous)
        self.play.clicked.connect(playback.play_pause)
        self.next.clicked.connect(playback.next)
        controls = QHBoxLayout()
        for button in (self.previous, self.play, self.next): controls.addWidget(button)
        details = QVBoxLayout()
        details.addWidget(self.title)
        details.addWidget(self.artist)
        details.addLayout(controls)
        layout = QHBoxLayout(self)
        layout.addWidget(self.cover)
        layout.addLayout(details)
        self.resize(350, 130)
        position = settings.get(self.POSITION_KEY) if settings else None
        if (isinstance(position, list) and len(position) == 2
                and all(isinstance(v, int) and not isinstance(v, bool) for v in position)):
            self.move(*position)
        self._listener = _Listener(self)
        playback.add_listener(self._listener)
        listener = self._listener
        self.destroyed.connect(lambda: playback.remove_listener(listener))
        page._result.ready.connect(self._cover_ready)
        self.on_track_changed(playback.current)
        self.on_state_changed(playback.state)

    def on_track_changed(self, track):
        self.title.setText(track.title if track else "Nada tocando")
        self.artist.setText(track.display_artist if track else "")
        self._update_cover()

    def _update_cover(self):
        pixmap = self.page.cover.pixmap()
        if pixmap:
            self.cover.setPixmap(pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))

    @Slot(int, QImage)
    def _cover_ready(self, generation, image):
        if generation == self.page._generation and not self.page._stopped.is_set():
            self._update_cover()

    def on_state_changed(self, state):
        self.play.setText("⏸" if state is PlayerState.PLAYING else "▶")
    def on_position_changed(self, position, duration): pass
    def on_queue_changed(self): pass
    def on_track_unavailable(self, track, message): pass
    def on_settings_changed(self): pass

    def closeEvent(self, event):
        if self.settings is not None:
            self.settings.set(self.POSITION_KEY, [self.x(), self.y()])
        super().closeEvent(event)

    def shutdown(self):
        self.close()
        self.playback.remove_listener(self._listener)
