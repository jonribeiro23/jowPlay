"""Árvore de navegação à esquerda: Biblioteca (Músicas, Artistas, Álbuns, Gêneros), Playlists e Extrair."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from ytdown.presentation.qt import theme
from ytdown.presentation.qt.pages import PageId

LIBRARY_LABEL = "Biblioteca"
_LIBRARY_PAGES = (PageId.SONGS, PageId.ARTISTS, PageId.ALBUMS, PageId.GENRES)
_TOP_LEVEL_PAGES = (PageId.PLAYLISTS, PageId.EXTRACT)
_PAGE_ROLE = Qt.ItemDataRole.UserRole
PAGE_ICONS = {
    PageId.SONGS: "songs",
    PageId.ARTISTS: "artists",
    PageId.ALBUMS: "albums",
    PageId.GENRES: "genres",
    PageId.PLAYLISTS: "playlists",
    PageId.EXTRACT: "extract",
}
LIBRARY_ICON = "library"


class NavigationPane(QTreeWidget):
    page_selected = Signal(PageId)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("navigation")
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.setRootIsDecorated(True)
        self.setMinimumWidth(160)
        size = theme.METRICS["nav_icon_size"]
        self.setIconSize(QSize(size, size))
        self._items: dict[PageId, QTreeWidgetItem] = {}

        library = QTreeWidgetItem(self, [LIBRARY_LABEL])
        library.setIcon(0, theme.icon(LIBRARY_ICON))
        library.setFlags(Qt.ItemFlag.ItemIsEnabled)  # Só agrupa; não é uma página.
        for page in _LIBRARY_PAGES:
            self._add(page, library)
        for page in _TOP_LEVEL_PAGES:
            self._add(page, self)
        library.setExpanded(True)

        self.currentItemChanged.connect(self._on_current_item_changed)

    def _add(self, page: PageId, parent) -> None:
        item = QTreeWidgetItem(parent, [page.title])
        item.setIcon(0, theme.icon(PAGE_ICONS[page]))
        item.setData(0, _PAGE_ROLE, page)
        self._items[page] = item

    def select(self, page: PageId) -> None:
        self.setCurrentItem(self._items[page])

    def current_page(self) -> PageId | None:
        item = self.currentItem()
        return item.data(0, _PAGE_ROLE) if item else None

    def set_counts(self, tracks) -> None:
        counts = {
            PageId.SONGS: len(tracks.list_tracks()),
            PageId.ARTISTS: len(tracks.artists()),
            PageId.ALBUMS: len(tracks.albums()),
            PageId.GENRES: len(tracks.genres()),
        }
        for page, count in counts.items():
            self._items[page].setText(1, str(count))
        self.resizeColumnToContents(0)

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        page = current.data(0, _PAGE_ROLE) if current else None
        if page is not None:
            self.page_selected.emit(page)
