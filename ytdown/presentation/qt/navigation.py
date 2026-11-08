"""Árvore de navegação à esquerda: Biblioteca (Músicas, Artistas, Álbuns, Gêneros), Playlists e Extrair."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from ytdown.presentation.qt.pages import PageId

LIBRARY_LABEL = "Biblioteca"
_LIBRARY_PAGES = (PageId.SONGS, PageId.ARTISTS, PageId.ALBUMS, PageId.GENRES)
_TOP_LEVEL_PAGES = (PageId.PLAYLISTS, PageId.EXTRACT)
_PAGE_ROLE = Qt.ItemDataRole.UserRole


class NavigationPane(QTreeWidget):
    page_selected = Signal(PageId)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("navigation")
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setMinimumWidth(160)
        self._items: dict[PageId, QTreeWidgetItem] = {}

        library = QTreeWidgetItem(self, [LIBRARY_LABEL])
        library.setFlags(Qt.ItemFlag.ItemIsEnabled)  # Só agrupa; não é uma página.
        for page in _LIBRARY_PAGES:
            self._add(page, library)
        for page in _TOP_LEVEL_PAGES:
            self._add(page, self)
        library.setExpanded(True)

        self.currentItemChanged.connect(self._on_current_item_changed)

    def _add(self, page: PageId, parent) -> None:
        item = QTreeWidgetItem(parent, [page.title])
        item.setData(0, _PAGE_ROLE, page)
        self._items[page] = item

    def select(self, page: PageId) -> None:
        self.setCurrentItem(self._items[page])

    def current_page(self) -> PageId | None:
        item = self.currentItem()
        return item.data(0, _PAGE_ROLE) if item else None

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        page = current.data(0, _PAGE_ROLE) if current else None
        if page is not None:
            self.page_selected.emit(page)
