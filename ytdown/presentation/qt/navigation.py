"""Árvore de navegação à esquerda: Biblioteca (Músicas, Artistas, Álbuns, Gêneros), Playlists e Extrair."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu, QInputDialog, QMessageBox
from ytdown.presentation.qt.songs_page import SongsTable, TRACKS_MIME

from ytdown.presentation.qt import theme
from ytdown.presentation.qt.pages import PageId
from ytdown.application.playlists import AutomaticPlaylist

LIBRARY_LABEL = "Biblioteca"
_LIBRARY_PAGES = (PageId.SONGS, PageId.RECENT, PageId.ARTISTS, PageId.ALBUMS, PageId.GENRES)
_TOP_LEVEL_PAGES = (PageId.NOW_PLAYING, PageId.PLAYLISTS, PageId.EXTRACT)
_PAGE_ROLE = Qt.ItemDataRole.UserRole
PAGE_ICONS = {
    PageId.NOW_PLAYING: "play",
    PageId.SONGS: "songs",
    PageId.RECENT: "songs",
    PageId.ARTISTS: "artists",
    PageId.ALBUMS: "albums",
    PageId.GENRES: "genres",
    PageId.PLAYLISTS: "playlists",
    PageId.EXTRACT: "extract",
}
LIBRARY_ICON = "library"


class NavigationPane(QTreeWidget):
    page_selected = Signal(PageId)
    playlist_selected = Signal(int)

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
        self._playlist_service = None

    def bind_playlists(self, service, page):
        self._playlist_service, self._playlist_page = service, page
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._playlist_menu)
        page.save_button.clicked.connect(lambda: self.create_playlist(page.playlist.tracks) if page.playlist else None)
        self.refresh_playlists()

    def refresh_playlists(self, selected=None):
        root = self._items[PageId.PLAYLISTS]
        self.blockSignals(True)
        try:
            root.takeChildren()
            for playlist in self._playlist_service.playlists.list_playlists():
                item = QTreeWidgetItem(root, [playlist.name])
                item.setData(0, _PAGE_ROLE, PageId.PLAYLISTS)
                item.setData(0, Qt.ItemDataRole.UserRole + 1, playlist.id)
                if playlist.id == selected:
                    self.setCurrentItem(item)
            if self._playlist_page.automatic_playlists is not None:
                for kind in AutomaticPlaylist:
                    item = QTreeWidgetItem(root, [kind.value])
                    item.setData(0, _PAGE_ROLE, PageId.PLAYLISTS)
                    item.setData(0, Qt.ItemDataRole.UserRole + 2, kind.value)
            root.setExpanded(True)
        finally:
            self.blockSignals(False)
        self._playlist_page.refresh()

    def create_playlist(self, queue=None):
        name, ok = QInputDialog.getText(self, 'Nova playlist', 'Nome:')
        if not ok:
            return
        try:
            playlist = (self._playlist_service.create(name) if queue is None else
                        self._playlist_service.save_queue(name, queue))
        except ValueError as exc:
            QMessageBox.warning(self, 'Playlist', str(exc))
            return
        self.refresh_playlists(playlist.id)
        self._select_playlist(playlist.id)

    def _select_playlist(self, playlist_id):
        self._playlist_page.select_playlist(playlist_id)
        self.playlist_selected.emit(playlist_id)

    def _playlist_menu(self, position):
        item = self.itemAt(position)
        if item is None or item.data(0, _PAGE_ROLE) is not PageId.PLAYLISTS:
            return
        self.setCurrentItem(item)
        playlist_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        automatic = item.data(0, Qt.ItemDataRole.UserRole + 2)
        menu = QMenu(self)
        menu.addAction('Nova playlist', lambda: self.create_playlist())
        if playlist_id is not None:
            menu.addAction('Renomear', self.rename_playlist)
            menu.addAction('Excluir', self.delete_playlist)
        if automatic is not None:
            menu.addAction('Salvar como playlist', lambda: self.create_playlist(self._playlist_page.playlist.tracks))
        menu.exec(self.viewport().mapToGlobal(position))

    def rename_playlist(self):
        item = self.currentItem()
        playlist_id = item.data(0, Qt.ItemDataRole.UserRole + 1) if item else None
        if playlist_id is None:
            return
        name, ok = QInputDialog.getText(self, 'Renomear playlist', 'Nome:', text=item.text(0))
        if ok:
            try:
                self._playlist_service.rename(playlist_id, name)
                self.refresh_playlists(playlist_id)
            except ValueError as exc:
                QMessageBox.warning(self, 'Playlist', str(exc))

    def delete_playlist(self):
        item = self.currentItem()
        playlist_id = item.data(0, Qt.ItemDataRole.UserRole + 1) if item else None
        if playlist_id is not None and QMessageBox.question(self, 'Excluir playlist',
                f'Excluir a playlist “{item.text(0)}”?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._playlist_service.delete(playlist_id)
            self._playlist_page.select_playlist(None)
            self.refresh_playlists()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F2 and self._playlist_service is not None:
            self.rename_playlist()
            event.accept()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if isinstance(event.source(), SongsTable) and event.mimeData().hasFormat(TRACKS_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if isinstance(event.source(), SongsTable) and item and item.data(0, Qt.ItemDataRole.UserRole + 1) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if not isinstance(event.source(), SongsTable) or not item:
            event.ignore()
            return
        playlist_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if playlist_id is None:
            event.ignore()
            return
        source = event.source()
        rows = sorted(index.row() for index in source.selectionModel().selectedRows())
        self.add_tracks(playlist_id, [source.model().tracks[row] for row in rows])
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def add_tracks(self, playlist_id, tracks):
        try:
            self._playlist_service.add_tracks(playlist_id, [track.id for track in tracks])
            self._playlist_page.refresh()
        except ValueError as exc:
            QMessageBox.warning(self, 'Playlist', str(exc))

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
            playlist_id = current.data(0, Qt.ItemDataRole.UserRole + 1)
            automatic = current.data(0, Qt.ItemDataRole.UserRole + 2)
            if page is PageId.PLAYLISTS and self._playlist_service is not None:
                if automatic is not None:
                    self._playlist_page.select_automatic(AutomaticPlaylist(automatic))
                elif playlist_id is None:
                    self._playlist_page.select_playlist(None)
                else:
                    self._select_playlist(playlist_id)
