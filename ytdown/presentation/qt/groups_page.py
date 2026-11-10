"""Navegação por artistas e gêneros da biblioteca."""
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Signal, QSize
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QListView,
                               QPushButton, QStackedWidget, QTableView, QVBoxLayout, QWidget)

from ytdown.domain.library import TrackQuery, summarize_albums, summarize_artists, summarize_genres
from ytdown.presentation.qt.songs_page import TrackTableModel
from ytdown.presentation.qt.track_actions import TrackActions


class GroupsModel(QAbstractListModel):
    def __init__(self, repository, kind, parent=None):
        super().__init__(parent)
        self.repository, self.kind = repository, kind
        self.text = ""
        self.visible = []
        self.refresh()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.visible)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.visible):
            return None
        item = self.visible[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if self.kind == "artist":
                return f"{item.name}  ·  {item.album_count} álbuns  ·  {item.track_count} faixas"
            return f"{item.name}  ·  {item.track_count} faixas"
        return None

    def refresh(self):
        tracks = self.repository.list_tracks()
        summaries = summarize_artists(tracks) if self.kind == "artist" else summarize_genres(tracks)
        matching = self.repository.list_tracks(TrackQuery(text=self.text))
        names = {t.display_artist if self.kind == "artist" else t.display_genre for t in matching}
        self.beginResetModel()
        self.visible = [item for item in summaries if item.name in names]
        self.endResetModel()


class GroupsPage(QWidget):
    detail_changed = Signal(str)

    def __init__(self, repository, playback, kind, storage=None, send_to_phone=None):
        super().__init__()
        self.repository, self.playback, self.kind = repository, playback, kind
        self.current_key = None
        self.model = GroupsModel(repository, kind, self)
        title = "Artistas" if kind == "artist" else "Gêneros"
        layout = QVBoxLayout(self)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        listing = QWidget()
        listing_layout = QVBoxLayout(listing)
        listing_layout.addWidget(QLabel(title))
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.activated.connect(self.open_index)
        listing_layout.addWidget(self.view)
        self.open_button = QPushButton("Abrir")
        self.open_button.clicked.connect(lambda: self.open_index(self.view.currentIndex()))
        listing_layout.addWidget(self.open_button)
        self.stack.addWidget(listing)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        back = QPushButton("‹ " + title)
        back.clicked.connect(self.show_list)
        detail_layout.addWidget(back)
        heading = QHBoxLayout()
        self.details = QLabel()
        heading.addWidget(self.details, 1)
        self.play_button = QPushButton("Tocar tudo")
        self.play_button.clicked.connect(self.play_current)
        heading.addWidget(self.play_button)
        detail_layout.addLayout(heading)
        self.albums = QListView()
        if kind == "artist":
            from PySide6.QtCore import QStringListModel
            self.album_model = QStringListModel(self)
            self.albums.setModel(self.album_model)
            self.albums.setViewMode(QListView.ViewMode.IconMode)
            self.albums.setResizeMode(QListView.ResizeMode.Adjust)
            self.albums.setGridSize(QSize(180, 65))
            detail_layout.addWidget(QLabel("Álbuns"))
            detail_layout.addWidget(self.albums)
        self.track_model = TrackTableModel(repository, self)
        self.table = QTableView()
        self.table.setModel(self.track_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_actions = TrackActions(self.table, playback, storage, send_to_phone)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.activated.connect(lambda index: self.playback.play_tracks(self.track_model.tracks, index.row()))
        detail_layout.addWidget(QLabel("Faixas"))
        detail_layout.addWidget(self.table, 1)
        self.stack.addWidget(detail)

    def set_search_text(self, text):
        self.model.text = text
        self.model.refresh()

    def open_index(self, index):
        if index.isValid() and index.row() < len(self.model.visible):
            self.current_key = (self.model.visible[index.row()].name,)
            self._refresh_detail()
            self.stack.setCurrentIndex(1)
            self.detail_changed.emit(self.current_key[0])

    def _refresh_detail(self):
        name = self.current_key[0]
        query = TrackQuery(**{self.kind: name})
        tracks = self.repository.list_tracks(query)
        if not tracks:
            self.show_list()
            return
        self.track_model.beginResetModel()
        self.track_model.tracks = tracks
        self.track_model.endResetModel()
        self.details.setText(f"{name}  ·  {len(tracks)} faixas")
        if self.kind == "artist":
            self.album_model.setStringList([f"{a.title}\n{a.track_count} faixas" for a in summarize_albums(tracks)])

    def show_list(self):
        self.current_key = None
        self.stack.setCurrentIndex(0)
        self.detail_changed.emit("")

    def play_current(self):
        if self.current_key and self.track_model.tracks:
            self.playback.play_tracks(self.track_model.tracks)

    def refresh(self):
        self.model.refresh()
        if self.current_key:
            self._refresh_detail()
