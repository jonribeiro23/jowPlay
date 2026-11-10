"""Interface de playlists; cada linha corresponde a uma ocorrência."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from ytdown.presentation.qt.track_actions import send_tracks_to_phone
from ytdown.presentation.qt.transport_bar import _time
from ytdown.application.playlists import AutomaticPlaylist


class PlaylistList(QListWidget):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        if self.page.automatic is not None:
            event.ignore()
            return
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
    def __init__(self, service, playback, automatic_playlists=None, storage=None, send_to_phone=None):
        super().__init__()
        self.service, self.playback = service, playback
        self.storage, self.send_to_phone = storage, send_to_phone
        self.playlist_id = None
        self.automatic_playlists = automatic_playlists
        self.automatic = None
        playback.add_listener(self)
        self.title = QLabel('Selecione uma playlist')
        self.title.setObjectName('pageTitle')
        self.items = PlaylistList(self)
        self.items.itemDoubleClicked.connect(lambda item: self.play(self.items.row(item)))
        self.total = QLabel()
        self.play_button = QPushButton('Tocar')
        self.play_button.clicked.connect(lambda: self.play(0))
        self.send_button = QPushButton('Enviar para o celular')
        self.send_button.setVisible(self.can_send)
        self.send_button.clicked.connect(self.send_current)
        self.save_button = QPushButton('Salvar como playlist')
        row = QHBoxLayout()
        row.addWidget(self.play_button)
        row.addWidget(self.send_button)
        row.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.items, 1)
        layout.addWidget(self.total)
        layout.addLayout(row)
        self.refresh()

    def select_playlist(self, playlist_id):
        self.automatic = None
        self.playlist_id = playlist_id
        self.refresh()

    def select_automatic(self, kind):
        self.playlist_id = None
        self.automatic = kind
        self.refresh()

    def refresh(self):
        self.playlist = (self.automatic_playlists.get(self.automatic) if self.automatic is not None else
                         self.service.playlists.get(self.playlist_id) if self.playlist_id is not None else None)
        self.items.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop if self.automatic is not None
                                   else QAbstractItemView.DragDropMode.InternalMove)
        self.items.clear()
        tracks = self.playlist.tracks if self.playlist else ()
        self.title.setText(self.playlist.name if self.playlist else 'Selecione uma playlist')
        for track in tracks:
            self.items.addItem(QListWidgetItem(f'{track.title} — {track.display_artist}  {_time(track.duration_ms)}'))
        self.total.setText(f'{len(tracks)} faixas · {_time(sum(max(0, t.duration_ms) for t in tracks))}')
        self.play_button.setEnabled(bool(tracks))
        self.send_button.setEnabled(bool(tracks))
        self.save_button.setVisible(self.automatic is not None)
        self.save_button.setEnabled(bool(tracks))

    @property
    def can_send(self):
        return self.storage is not None and self.send_to_phone is not None

    def send_current(self):
        """Envia a playlist inteira (manual ou automática) ao celular."""
        if self.can_send and self.playlist and self.playlist.tracks:
            send_tracks_to_phone(self, self.storage, self.send_to_phone, list(self.playlist.tracks))

    def play(self, row):
        if self.playlist and self.playlist.tracks:
            self.playback.play_tracks(list(self.playlist.tracks), row)

    def move(self, source, destination):
        if self.automatic is not None:
            return
        self.service.move_track(self.playlist_id, source, destination)
        self.refresh()

    def remove_selected(self):
        if self.automatic is not None:
            return
        for row in sorted((self.items.row(item) for item in self.items.selectedItems()), reverse=True):
            self.service.remove_track(self.playlist_id, row)
        self.refresh()

    def on_play_recorded(self, track):
        if self.automatic is AutomaticPlaylist.MOST_PLAYED:
            self.refresh()

    def detach_playback(self):
        self.playback.remove_listener(self)

    def on_track_changed(self, track): pass
    def on_state_changed(self, state): pass
    def on_position_changed(self, position, duration): pass
    def on_queue_changed(self): pass
    def on_track_unavailable(self, track, message): pass
