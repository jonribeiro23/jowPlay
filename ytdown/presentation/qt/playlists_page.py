"""Interface de playlists; cada linha corresponde a uma ocorrência."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from ytdown.presentation.qt.transport_bar import _time


class PlaylistList(QListWidget):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        rows = sorted(self.row(item) for item in self.selectedItems())
        if event.source() is not self or len(rows) != 1:
            event.ignore()
            return
        item = self.itemAt(event.position().toPoint())
        target = self.row(item) if item else self.count()
        if item and event.position().y() > self.visualItemRect(item).center().y():
            target += 1
        target -= target > rows[0]
        if target != rows[0]:
            self.page.move(rows[0], target)
            self.setCurrentRow(target)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.page.remove_selected()
            event.accept()
            return
        super().keyPressEvent(event)


class PlaylistsPage(QWidget):
    def __init__(self, service, playback):
        super().__init__()
        self.service, self.playback = service, playback
        self.playlist_id = None
        self.title = QLabel('Selecione uma playlist')
        self.title.setObjectName('pageTitle')
        self.items = PlaylistList(self)
        self.items.itemDoubleClicked.connect(lambda item: self.play(self.items.row(item)))
        self.total = QLabel()
        self.play_button = QPushButton('Tocar')
        self.play_button.clicked.connect(lambda: self.play(0))
        self.send_button = QPushButton('Enviar para o celular')
        row = QHBoxLayout()
        row.addWidget(self.play_button)
        row.addWidget(self.send_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.items, 1)
        layout.addWidget(self.total)
        layout.addLayout(row)
        self.refresh()

    def select_playlist(self, playlist_id):
        self.playlist_id = playlist_id
        self.refresh()

    def refresh(self):
        self.playlist = self.service.playlists.get(self.playlist_id) if self.playlist_id is not None else None
        self.items.clear()
        tracks = self.playlist.tracks if self.playlist else ()
        self.title.setText(self.playlist.name if self.playlist else 'Selecione uma playlist')
        for track in tracks:
            self.items.addItem(QListWidgetItem(f'{track.title} — {track.display_artist}  {_time(track.duration_ms)}'))
        self.total.setText(f'{len(tracks)} faixas · {_time(sum(max(0, t.duration_ms) for t in tracks))}')
        self.play_button.setEnabled(bool(tracks))
        self.send_button.setEnabled(bool(tracks))

    def play(self, row):
        if self.playlist and self.playlist.tracks:
            self.playback.play_tracks(list(self.playlist.tracks), row)

    def move(self, source, destination):
        self.service.move_track(self.playlist_id, source, destination)
        self.refresh()

    def remove_selected(self):
        for row in sorted((self.items.row(item) for item in self.items.selectedItems()), reverse=True):
            self.service.remove_track(self.playlist_id, row)
        self.refresh()
