"""Painel "Lista de reprodução" à direita. Por enquanto, só a estrutura (JOW-29)."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget

TITLE = "Lista de reprodução"
EMPTY_MESSAGE = "A lista de reprodução está vazia."


class PlayQueuePane(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("playQueuePane")
        self.setMinimumWidth(200)

        title = QLabel(TITLE)
        title.setObjectName("paneTitle")
        self.items = QListWidget()
        self.items.setObjectName("playQueue")
        self.empty_message = QLabel(EMPTY_MESSAGE)
        self.empty_message.setObjectName("paneHint")
        self.empty_message.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(title)
        layout.addWidget(self.empty_message)
        layout.addWidget(self.items, stretch=1)
