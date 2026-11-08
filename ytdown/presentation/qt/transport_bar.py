"""Barra de controles inferior, como a do WMP 7. Por enquanto, sem ação (JOW-28).

Em cima, a posição da música; embaixo, o que está tocando à esquerda, os controles no centro
(o botão de tocar maior, no meio) e o volume à direita.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QVBoxLayout, QWidget

from ytdown.presentation.qt import theme

PLAY_BUTTON_SIZE = theme.METRICS["play_button_size"]
BUTTON_SIZE = theme.METRICS["button_size"]


def _button(name: str, icon: str, tooltip: str, size: int = BUTTON_SIZE,
            icon_size: int = theme.METRICS["icon_size"]) -> QToolButton:
    button = QToolButton()
    button.setObjectName(name)
    button.setIcon(theme.icon(icon))
    button.setIconSize(QSize(icon_size, icon_size))
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setFixedSize(size, size)
    button.setEnabled(False)  # Os controles passam a funcionar com o player (JOW-24 e JOW-28).
    return button


class TransportBar(QWidget):
    queue_pane_toggled = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("transportBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)  # Para o gradiente do tema.

        self.now_playing = QLabel("Nada tocando")
        self.now_playing.setObjectName("nowPlaying")
        self.now_playing.setMinimumWidth(160)

        self.shuffle_button = _button("shuffleButton", "shuffle", "Aleatório")
        self.previous_button = _button("previousButton", "previous", "Anterior")
        self.play_button = _button("playButton", "play", "Tocar", PLAY_BUTTON_SIZE,
                                   theme.METRICS["play_icon_size"])
        self.next_button = _button("nextButton", "next", "Próxima")
        self.repeat_button = _button("repeatButton", "repeat", "Repetir")

        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setObjectName("positionSlider")
        self.position.setAccessibleName("Posição")
        self.position.setEnabled(False)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("timeLabel")

        self.mute_button = _button("muteButton", "volume", "Mudo")
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

        self._build()

    def _build(self) -> None:
        position_row = QHBoxLayout()
        position_row.addWidget(self.position, stretch=1)
        position_row.addWidget(self.time_label)

        # As laterais têm o mesmo peso, então os controles ficam exatamente no centro.
        left = QHBoxLayout()
        left.addWidget(self.now_playing, stretch=1)
        center = QHBoxLayout()
        center.setSpacing(theme.METRICS["space_s"])
        for button in (self.shuffle_button, self.previous_button, self.play_button, self.next_button,
                       self.repeat_button):
            center.addWidget(button, alignment=Qt.AlignmentFlag.AlignVCenter)
        right = QHBoxLayout()
        right.addStretch()
        right.addWidget(self.mute_button)
        right.addWidget(self.volume)
        right.addSpacing(theme.METRICS["space_m"])
        right.addWidget(self.queue_toggle)

        controls_row = QHBoxLayout()
        controls_row.addLayout(left, stretch=1)
        controls_row.addLayout(center)
        controls_row.addLayout(right, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.METRICS["space_m"], theme.METRICS["space_xs"],
                                  theme.METRICS["space_m"], theme.METRICS["space_s"])
        layout.setSpacing(theme.METRICS["space_xs"])
        layout.addLayout(position_row)
        layout.addLayout(controls_row)

    def controls(self) -> list[QWidget]:
        return [self.shuffle_button, self.previous_button, self.play_button, self.next_button,
                self.repeat_button, self.position, self.mute_button, self.volume]
