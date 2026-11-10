"""Barra de controles inferior ligada exclusivamente ao caso de uso Playback.

Em cima, a posição da música; embaixo, o que está tocando à esquerda, os controles no centro
(o botão de tocar maior, no meio) e o volume à direita.
"""

from __future__ import annotations

import queue
import threading
import weakref
from collections.abc import Callable

from PySide6.QtCore import QObject, QSize, Qt, Signal, QSignalBlocker, Slot, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget

from ytdown.application.playback import Playback
from ytdown.application.ports import PlayerState
from ytdown.domain.library import Track
from ytdown.domain.play_queue import RepeatMode
from ytdown.presentation.qt import theme

PLAY_BUTTON_SIZE = theme.METRICS["play_button_size"]
BUTTON_SIZE = theme.METRICS["button_size"]


class _Listener:
    """O Playback não mantém a janela viva; remoção explícita ao fechar/destruir."""

    def __init__(self, bar):
        self.bar = weakref.ref(bar)

    def __getattr__(self, name):
        def notify(*args):
            bar = self.bar()
            if bar is not None:
                getattr(bar, name)(*args)
        return notify


class _CoverResult(QObject):
    ready = Signal(int, QImage)


def _read_covers(requests, stopped, result, read_cover):
    """Uma leitura por vez; fila limitada à solicitação mais recente."""
    while not stopped.is_set():
        request = requests.get()
        if request is None or stopped.is_set():
            return
        generation, track = request
        image = QImage()
        try:
            data = read_cover(track)
            if data:
                image = QImage.fromData(data).scaled(
                    48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
        except Exception:
            pass  # Capa ausente/ilegível não impede ouvir a faixa.
        if not stopped.is_set():
            result.ready.emit(generation, image)


def _latest(requests, value):
    try:
        requests.get_nowait()
    except queue.Empty:
        pass
    requests.put_nowait(value)


def _time(ms):
    seconds = max(0, ms) // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def _button(name: str, icon: str, tooltip: str, size: int = BUTTON_SIZE,
            icon_size: int = theme.METRICS["icon_size"]) -> QToolButton:
    button = QToolButton()
    button.setObjectName(name)
    button.setIcon(theme.icon(icon))
    button.setIconSize(QSize(icon_size, icon_size))
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setFixedSize(size, size)
    button.setEnabled(False)
    return button


class TransportBar(QWidget):
    queue_pane_toggled = Signal(bool)
    now_playing_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("transportBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)  # Para o gradiente do tema.
        self._playback = None
        self._generation = 0
        self._dragging = False
        self._duration = 0
        self._requests = queue.Queue(maxsize=1)
        self._stopped = threading.Event()
        self._worker = None
        self._has_requested = False
        self._cover_result = _CoverResult()
        self._cover_result.ready.connect(self._cover_ready)
        self._default_cover = QPixmap()
        self.cover = QLabel()
        self.cover.setObjectName("nowPlayingCover")
        self.cover.setFixedSize(48, 48)
        self.cover.setAccessibleName("Capa da faixa")
        self.cover.mouseDoubleClickEvent = lambda event: self.now_playing_requested.emit()
        self.artist = QLabel()
        self.artist.setObjectName("nowPlayingArtist")

        self.now_playing = QLabel("Nada tocando")
        self.now_playing.setObjectName("nowPlaying")
        self.now_playing.setTextFormat(Qt.TextFormat.PlainText)
        self.artist.setTextFormat(Qt.TextFormat.PlainText)
        for label in (self.now_playing, self.artist):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.now_playing.setMaximumWidth(260)
        self.artist.setMaximumWidth(260)

        self.shuffle_button = _button("shuffleButton", "shuffle", "Aleatório")
        self.previous_button = _button("previousButton", "previous", "Anterior")
        self.play_button = _button("playButton", "play", "Tocar", PLAY_BUTTON_SIZE,
                                   theme.METRICS["play_icon_size"])
        self.next_button = _button("nextButton", "next", "Próxima")
        self.repeat_button = _button("repeatButton", "repeat", "Repetir")
        for button in (self.shuffle_button, self.repeat_button):
            button.setCheckable(True)

        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setObjectName("positionSlider")
        self.position.setAccessibleName("Posição")
        self.position.setEnabled(False)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("timeLabel")

        self.mute_button = _button("muteButton", "volume", "Mudo")
        self.mute_button.setCheckable(True)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("volumeSlider")
        self.volume.setAccessibleName("Volume")
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(100)
        self.volume.setEnabled(False)

        self.queue_toggle = QToolButton()
        self.queue_toggle.setObjectName("queueToggle")
        self.queue_toggle.setText("Lista")
        self.queue_toggle.setIcon(theme.icon("queue"))
        self.queue_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.queue_toggle.setFixedHeight(BUTTON_SIZE)
        self.queue_toggle.setToolTip("Mostrar ou esconder a lista de reprodução (Ctrl+L)")
        self.queue_toggle.setCheckable(True)
        self.queue_toggle.setChecked(True)
        self.queue_toggle.toggled.connect(self.queue_pane_toggled)
        self.now_playing_button = QToolButton()
        self.now_playing_button.setText("Em reprodução")
        self.now_playing_button.setToolTip("Abrir Em reprodução")
        self.now_playing_button.clicked.connect(self.now_playing_requested)

        self._build()

    def bind(self, playback: Playback, read_cover: Callable[[Track], bytes | None] | None = None,
             default_cover: QPixmap | None = None) -> None:
        """Montagem explícita no bootstrap; sem bind, os controles são placeholders."""
        if self._playback is not None:
            raise RuntimeError("TransportBar já ligada ao Playback")
        self._playback = playback
        self._listener = _Listener(self)
        playback.add_listener(self._listener)
        listener, requests, stopped = self._listener, self._requests, self._stopped

        def cleanup():
            playback.remove_listener(listener)
            stopped.set()
            _latest(requests, None)

        self._cleanup = cleanup
        self.destroyed.connect(cleanup)
        if default_cover is not None:
            self._default_cover = default_cover.scaled(
                self.cover.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        if read_cover is not None:
            self._worker = threading.Thread(target=_read_covers,
                                            args=(requests, stopped, self._cover_result, read_cover),
                                            daemon=True, name="transport-cover")
            self._worker.start()
        self._read_cover = read_cover
        self.play_button.clicked.connect(playback.play_pause)
        self.previous_button.clicked.connect(playback.previous)
        self.next_button.clicked.connect(playback.next)
        self.shuffle_button.clicked.connect(playback.set_shuffle)
        self.repeat_button.clicked.connect(playback.cycle_repeat)
        self.mute_button.clicked.connect(playback.set_muted)
        self.volume.valueChanged.connect(playback.set_volume)
        self.position.sliderPressed.connect(self._begin_seek)
        self.position.sliderReleased.connect(self._end_seek)
        self.position.valueChanged.connect(self._seek_changed)
        for control in self.controls():
            control.setEnabled(True)
        self.on_track_changed(playback.current)
        self.on_state_changed(playback.state)
        self.on_settings_changed()
        self.on_position_changed(playback.position_ms, playback.duration_ms)

    def shutdown(self, retry=None) -> bool:
        self._generation += 1
        if self._playback is not None:
            self._cleanup()
        if self._has_requested and self._worker is not None and self._worker.is_alive():
            if retry is not None:
                QTimer.singleShot(25, retry)
            return False
        return True

    def _begin_seek(self):
        self._dragging = True

    def _end_seek(self):
        self._dragging = False
        self._playback.seek(self.position.value())

    def _seek_changed(self, value):
        self.time_label.setText(f"{_time(value)} / {_time(self._duration)}")
        if not self._dragging:
            self._playback.seek(value)

    def on_position_changed(self, position_ms, duration_ms):
        self._duration = max(0, duration_ms) if self._playback.current else 0
        if not self._dragging:
            with QSignalBlocker(self.position):
                self.position.setRange(0, min(self._duration, 2_147_483_647))
                self.position.setValue(position_ms if self._playback.current else 0)
        self.time_label.setText(f"{_time(self.position.value())} / {_time(self._duration)}")
        self.position.setEnabled(self._playback.current is not None and self._duration > 0)

    def on_track_changed(self, track):
        self._generation += 1
        self._dragging = False
        self.now_playing.setText(track.title if track else "Nada tocando")
        self.artist.setText(track.display_artist if track else "")
        self.now_playing.setToolTip(self.now_playing.text())
        self.artist.setToolTip(self.artist.text())
        self.cover.setPixmap(self._default_cover)
        # O aviso antecede o load: posição/duração do player ainda podem ser da faixa anterior.
        self.on_position_changed(0, track.duration_ms if track else 0)
        if track is not None and self._read_cover is not None:
            self._has_requested = True
            _latest(self._requests, (self._generation, track))

    @Slot(int, QImage)
    def _cover_ready(self, generation, image):
        if not self._stopped.is_set() and generation == self._generation:
            self.cover.setPixmap(QPixmap.fromImage(image) if not image.isNull() else self._default_cover)

    def on_state_changed(self, state):
        playing = state is PlayerState.PLAYING
        self.play_button.setIcon(theme.icon("pause" if playing else "play"))
        label = "Pausar" if playing else "Tocar"
        self.play_button.setToolTip(label)
        self.play_button.setAccessibleName(label)
        if state is PlayerState.STOPPED:
            self.on_position_changed(self._playback.position_ms, self._playback.duration_ms)

    def on_queue_changed(self):
        self.shuffle_button.setChecked(self._playback.shuffle)

    def on_settings_changed(self):
        with QSignalBlocker(self.volume), QSignalBlocker(self.mute_button):
            self.volume.setValue(self._playback.volume)
            self.mute_button.setChecked(self._playback.muted)
        self.mute_button.setIcon(theme.icon("mute" if self._playback.muted else "volume"))
        label = "Ativar som" if self._playback.muted else "Mudo"
        self.mute_button.setToolTip(label)
        self.mute_button.setAccessibleName(label)
        mode = self._playback.repeat
        self.repeat_button.setChecked(mode is not RepeatMode.OFF)
        self.repeat_button.setText("1" if mode is RepeatMode.ONE else "")
        self.repeat_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        label = {RepeatMode.OFF: "Repetir: desligado", RepeatMode.ALL: "Repetir: todas",
                 RepeatMode.ONE: "Repetir: uma"}[mode]
        self.repeat_button.setToolTip(label)
        self.repeat_button.setAccessibleName(label)
        self.on_queue_changed()

    def on_track_unavailable(self, track, message):
        self.now_playing.setToolTip(message)

    def _build(self) -> None:
        position_row = QHBoxLayout()
        position_row.addWidget(self.position, stretch=1)
        position_row.addWidget(self.time_label)

        # As laterais têm o mesmo peso, então os controles ficam exatamente no centro.
        left = QHBoxLayout()
        left.addWidget(self.cover)
        details = QVBoxLayout()
        details.addWidget(self.now_playing)
        details.addWidget(self.artist)
        left.addLayout(details, stretch=1)
        left.addStretch()
        center = QHBoxLayout()
        center.setSpacing(theme.METRICS["space_s"])
        for button in (self.shuffle_button, self.previous_button, self.play_button, self.next_button,
                       self.repeat_button):
            center.addWidget(button, alignment=Qt.AlignmentFlag.AlignVCenter)
        right = QHBoxLayout()
        right.setSpacing(theme.METRICS["space_s"])
        right.addStretch()
        right.addWidget(self.mute_button)
        right.addWidget(self.volume)
        right.addSpacing(theme.METRICS["space_m"])
        right.addWidget(self.queue_toggle)
        right.addWidget(self.now_playing_button)

        controls_row = QGridLayout()
        controls_row.addLayout(left, 0, 0)
        controls_row.addLayout(center, 0, 1)
        controls_row.addLayout(right, 0, 2)
        # O maior mínimo das laterais é reservado em ambos os lados; o restante
        # também é dividido igualmente, independentemente do tamanho dos textos.
        side_minimum = (self.mute_button.width() + self.volume.width()
                        + self.queue_toggle.sizeHint().width() + self.now_playing_button.sizeHint().width()
                        + theme.METRICS["space_m"] + 3 * right.spacing())
        for column in (0, 2):
            controls_row.setColumnMinimumWidth(column, side_minimum)
            controls_row.setColumnStretch(column, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.METRICS["space_m"], theme.METRICS["space_xs"],
                                  theme.METRICS["space_m"], theme.METRICS["space_s"])
        layout.setSpacing(theme.METRICS["space_xs"])
        layout.addLayout(position_row)
        layout.addLayout(controls_row)

    def controls(self) -> list[QWidget]:
        return [self.shuffle_button, self.previous_button, self.play_button, self.next_button,
                self.repeat_button, self.position, self.mute_button, self.volume]
