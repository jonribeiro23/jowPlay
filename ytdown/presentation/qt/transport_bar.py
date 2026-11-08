"""Barra de controles inferior, como a do WMP 7. Por enquanto, sem ação (JOW-28)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QWidget

PLAY_BUTTON_SIZE = 44
BUTTON_SIZE = 32


def _button(name: str, text: str, tooltip: str, size: int = BUTTON_SIZE) -> QToolButton:
    button = QToolButton()
    button.setObjectName(name)
    button.setText(text)
    button.setToolTip(tooltip)
    button.setFixedSize(size, size)
    button.setEnabled(False)  # Os controles passam a funcionar com o player (JOW-24 e JOW-28).
    return button


class TransportBar(QWidget):
    queue_pane_toggled = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("transportBar")

        self.now_playing = QLabel("Nada tocando")
        self.now_playing.setObjectName("nowPlaying")
        self.now_playing.setMinimumWidth(160)

        self.shuffle_button = _button("shuffleButton", "🔀", "Aleatório")
        self.previous_button = _button("previousButton", "⏮", "Anterior")
        self.play_button = _button("playButton", "▶", "Tocar", PLAY_BUTTON_SIZE)
        play_font = self.play_button.font()
        play_font.setPointSizeF(play_font.pointSizeF() * 1.8)  # O símbolo sai minúsculo no tamanho padrão.
        self.play_button.setFont(play_font)
        self.next_button = _button("nextButton", "⏭", "Próxima")
        self.repeat_button = _button("repeatButton", "🔁", "Repetir")

        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setObjectName("positionSlider")
        self.position.setEnabled(False)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("timeLabel")

        self.mute_button = _button("muteButton", "🔊", "Mudo")
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("volumeSlider")
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(100)
        self.volume.setEnabled(False)

        self.queue_toggle = QToolButton()
        self.queue_toggle.setObjectName("queueToggle")
        self.queue_toggle.setText("Lista")
        self.queue_toggle.setToolTip("Mostrar ou esconder a lista de reprodução (Ctrl+L)")
        self.queue_toggle.setCheckable(True)
        self.queue_toggle.setChecked(True)
        self.queue_toggle.toggled.connect(self.queue_pane_toggled)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.addWidget(self.now_playing)
        for button in (self.shuffle_button, self.previous_button, self.play_button, self.next_button,
                       self.repeat_button):
            layout.addWidget(button)
        layout.addWidget(self.position, stretch=1)
        layout.addWidget(self.time_label)
        layout.addWidget(self.mute_button)
        layout.addWidget(self.volume)
        layout.addWidget(self.queue_toggle)

    def controls(self) -> list[QWidget]:
        return [self.shuffle_button, self.previous_button, self.play_button, self.next_button,
                self.repeat_button, self.position, self.mute_button, self.volume]
