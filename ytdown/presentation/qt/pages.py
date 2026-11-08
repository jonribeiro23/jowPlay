"""As páginas da área de conteúdo."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PageId(Enum):
    SONGS = "Músicas"
    ARTISTS = "Artistas"
    ALBUMS = "Álbuns"
    GENRES = "Gêneros"
    PLAYLISTS = "Playlists"
    EXTRACT = "Extrair"

    @property
    def title(self) -> str:
        return self.value


class PlaceholderPage(QWidget):
    """Página ainda não implementada: mostra só o título."""

    def __init__(self, page: PageId) -> None:
        super().__init__()
        self.setObjectName(f"page-{page.name.lower()}")
        layout = QVBoxLayout(self)
        title = QLabel(page.title)
        title.setObjectName("pageTitle")
        font = title.font()
        font.setPointSizeF(font.pointSizeF() * 1.6)
        title.setFont(font)
        layout.addWidget(title)
        hint = QLabel("Em construção.")
        hint.setObjectName("pageHint")
        layout.addWidget(hint)
        layout.addStretch()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
