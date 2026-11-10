"""Álbuns virtualizados, com capas carregadas fora da thread da interface."""
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel,
                               QListView, QPushButton, QStackedWidget, QTableView,
                               QVBoxLayout, QWidget)

from ytdown.domain.library import album_order, summarize_albums
from ytdown.domain.text import search_key
from ytdown.presentation.qt.songs_page import TrackTableModel
from ytdown.presentation.qt.track_actions import TrackActions


class AlbumModel(QAbstractListModel):
    cover_ready = Signal(object, object, int)

    def __init__(self, repository, storage, cache, default_cover, parent=None):
        super().__init__(parent)
        self.repository, self.storage, self.cache = repository, storage, cache
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="album-covers")
        self.cover_ready.connect(self._cover_ready)
        self.generation = 0
        self.closed = False
        self.icons = {}
        self.pending = set()
        self.default = QIcon(str(default_cover))
        self.albums, self.groups, self.visible = [], {}, []
        self.text = ""
        self.sort_field = 0
        self.refresh()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.visible)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.visible):
            return None
        album = self.visible[index.row()]
        key = (album.title, album.artist)
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{album.title}\n{album.artist}" + (f" · {album.year}" if album.year else "")
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{album.title} — {album.artist}"
        if role == Qt.ItemDataRole.DecorationRole:
            if key not in self.icons and key not in self.pending and not self.closed:
                self.pending.add(key)
                track = self.groups[key][0]
                generation = self.generation
                future = self.executor.submit(self._load, track.rel_path)
                future.add_done_callback(lambda f, k=key, g=generation: self._done(f, k, g))
            return self.icons.get(key, self.default)
        return None

    def _load(self, relative):
        try:
            return self.cache.get_or_create(self.storage.absolute(relative))
        except Exception:
            return None

    def _done(self, future, key, generation):
        if not self.closed and not future.cancelled():
            try:
                self.cover_ready.emit(key, future.result(), generation)
            except RuntimeError:
                pass  # A janela já foi destruída.

    def _cover_ready(self, key, path, generation):
        if self.closed or generation != self.generation:
            return
        self.pending.discard(key)
        icon = QIcon(str(path)) if path else self.default
        self.icons[key] = icon if not icon.isNull() else self.default
        for row, album in enumerate(self.visible):
            if (album.title, album.artist) == key:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])
                break

    def refresh(self):
        tracks = self.repository.list_tracks()
        groups = {}
        for track in tracks:
            groups.setdefault((track.display_album, track.display_artist), []).append(track)
        self.generation += 1
        self.pending.clear()
        self.icons.clear()
        self.groups = {key: album_order(group) for key, group in groups.items()}
        self.albums = summarize_albums(tracks)
        self._filter()

    def _filter(self):
        words = search_key(self.text).split()
        albums = [a for a in self.albums if all(w in search_key(a.title + " " + a.artist) for w in words)]
        if self.sort_field == 1:
            albums.sort(key=lambda a: (search_key(a.artist), search_key(a.title)))
        elif self.sort_field == 2:
            albums.sort(key=lambda a: (a.year is None, a.year or 0, search_key(a.title)))
        elif self.sort_field == 3:
            albums.sort(key=lambda a: min(t.added_at for t in self.groups[(a.title, a.artist)]), reverse=True)
        self.beginResetModel()
        self.visible = albums
        self.endResetModel()

    def shutdown(self):
        self.closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)


class AlbumView(QListView):
    open_requested = Signal(QModelIndex)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.open_requested.emit(self.currentIndex())
        else:
            super().keyPressEvent(event)


class AlbumsPage(QWidget):
    detail_changed = Signal(str)

    def __init__(self, repository, playback, storage, cache, default_cover):
        super().__init__()
        self.playback = playback
        self.model = AlbumModel(repository, storage, cache, default_cover, self)
        self.current_key = None
        layout = QVBoxLayout(self)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        grid_page = QWidget()
        grid_layout = QVBoxLayout(grid_page)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Álbuns"))
        controls.addStretch()
        controls.addWidget(QLabel("Ordenar por"))
        self.sort = QComboBox()
        self.sort.addItems(["Álbum", "Artista", "Ano", "Data de inclusão"])
        self.sort.currentIndexChanged.connect(self._sort)
        controls.addWidget(self.sort)
        self.open_button = QPushButton("Abrir álbum")
        self.open_button.clicked.connect(self.open_selected)
        controls.addWidget(self.open_button)
        grid_layout.addLayout(controls)
        self.view = AlbumView()
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setUniformItemSizes(True)
        self.view.setIconSize(QSize(150, 150))
        self.view.setGridSize(QSize(190, 210))
        self.view.setWordWrap(True)
        self.view.setModel(self.model)
        self.view.doubleClicked.connect(self.play_index)
        self.view.open_requested.connect(self.open_index)
        grid_layout.addWidget(self.view, 1)
        self.stack.addWidget(grid_page)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        back = QPushButton("‹ Álbuns")
        back.clicked.connect(self.show_grid)
        detail_layout.addWidget(back)
        heading = QHBoxLayout()
        self.cover = QLabel()
        self.cover.setFixedSize(150, 150)
        heading.addWidget(self.cover)
        self.details = QLabel()
        heading.addWidget(self.details, 1)
        self.play_button = QPushButton("Tocar álbum")
        self.play_button.clicked.connect(self.play_current)
        heading.addWidget(self.play_button)
        detail_layout.addLayout(heading)
        self.table = QTableView()
        self.track_model = TrackTableModel(repository, self)
        self.table.setModel(self.track_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_actions = TrackActions(self.table, playback, storage)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.activated.connect(lambda index: self.playback.play_tracks(self.track_model.tracks, index.row()))
        detail_layout.addWidget(self.table, 1)
        self.stack.addWidget(detail)
        self.model.dataChanged.connect(self._update_cover)

    def _sort(self, index):
        self.model.sort_field = index
        self.model._filter()

    def set_search_text(self, text):
        self.model.text = text
        self.model._filter()

    def open_selected(self):
        self.open_index(self.view.currentIndex())

    def open_index(self, index):
        if not index.isValid():
            return
        album = self.model.visible[index.row()]
        self.current_key = (album.title, album.artist)
        self.model.data(index, Qt.ItemDataRole.DecorationRole)
        self._show_detail(album)
        self.stack.setCurrentIndex(1)
        self.detail_changed.emit(album.title)

    def _show_detail(self, album):
        self.track_model.beginResetModel()
        self.track_model.tracks = list(self.model.groups[self.current_key])
        self.track_model.endResetModel()
        seconds = album.total_duration_ms // 1000
        self.details.setText(f"{album.title}\n{album.artist}\n{album.year or 'Ano desconhecido'} · {seconds // 60}:{seconds % 60:02d}")
        self._update_cover()

    def _update_cover(self, *args):
        if self.current_key:
            icon = self.model.icons.get(self.current_key, self.model.default)
            self.cover.setPixmap(icon.pixmap(150, 150))

    def show_grid(self):
        self.current_key = None
        self.stack.setCurrentIndex(0)
        self.detail_changed.emit("")

    def play_index(self, index):
        if index.isValid():
            album = self.model.visible[index.row()]
            self.playback.play_tracks(self.model.groups[(album.title, album.artist)])

    def play_current(self):
        if self.current_key in self.model.groups:
            self.playback.play_tracks(self.model.groups[self.current_key])

    def refresh(self):
        self.model.refresh()
        if self.current_key:
            album = next((a for a in self.model.albums if (a.title, a.artist) == self.current_key), None)
            if album:
                self._show_detail(album)
            else:
                self.show_grid()

    def shutdown(self, callback=None):
        self.model.shutdown()
        return True
