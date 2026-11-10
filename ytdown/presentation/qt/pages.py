"""As páginas da área de conteúdo."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ytdown.presentation.qt import theme


class PageId(Enum):
    SONGS = "Músicas"
    RECENT = "Adicionadas recentemente"
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
        layout.setContentsMargins(*[theme.PAGE_MARGIN] * 4)
        title = QLabel(page.title)
        title.setObjectName("pageTitle")  # Tamanho e cor vêm do tema.
        layout.addWidget(title)
        hint = QLabel("Em construção.")
        hint.setObjectName("pageHint")
        layout.addWidget(hint)
        layout.addStretch()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
