"""Ações comuns às tabelas de faixas da biblioteca."""
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QAbstractItemView, QMenu, QMessageBox

from ytdown.domain.errors import LibraryError, ShareError


class TrackActions:
    def __init__(self, table, playback, storage=None, send_to_phone=None):
        self.table, self.playback, self.storage = table, playback, storage
        self.send_to_phone = send_to_phone
        self.delete_tracks = None
        self.refresh_library = None
        self.playlist_navigation = None
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self.open_menu)
        self.shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), table)
        self.shortcut.activated.connect(self.delete_selected)

    def selected_tracks(self):
        rows = sorted(index.row() for index in self.table.selectionModel().selectedRows())
        return [self.table.model().tracks[row] for row in rows]

    def make_menu(self):
        tracks = self.selected_tracks()
        menu = QMenu(self.table)
        if not tracks:
            return menu
        menu.addAction("Tocar", lambda: self.playback.play_tracks(tracks))
        menu.addAction("Tocar em seguida", lambda: self.playback.play_next(tracks))
        menu.addAction("Adicionar à fila", lambda: self.playback.append(tracks))
        if self.playlist_navigation is not None:
            submenu = menu.addMenu("Adicionar à playlist")
            for playlist in self.playlist_navigation._playlist_service.playlists.list_playlists():
                submenu.addAction(playlist.name, lambda checked=False, playlist_id=playlist.id:
                                  self.playlist_navigation.add_tracks(playlist_id, tracks))
            submenu.setEnabled(bool(submenu.actions()))
        if self.storage is not None and self.send_to_phone is not None:
            menu.addAction("Enviar para o celular", lambda: self.send_tracks(tracks))
        if self.delete_tracks is not None:
            menu.addAction("Excluir da biblioteca", self.delete_selected)
        if self.storage is not None and sys.platform == "win32" and len(tracks) == 1:
            try:
                path = self.storage.absolute(tracks[0].rel_path)
                if path.is_file():
                    menu.addAction("Mostrar no Explorer", lambda: subprocess.Popen(["explorer.exe", "/select,", str(path)]))
            except (LibraryError, OSError):
                pass
        return menu

    def send_tracks(self, tracks):
        paths, missing = [], []
        for track in tracks:
            try:
                path = self.storage.absolute(track.rel_path)
                if track.missing or not path.is_file():
                    missing.append(track.title)
                else:
                    paths.append(path)
            except (LibraryError, OSError):
                missing.append(track.title)
        if missing:
            QMessageBox.warning(self.table, "Faixas indisponíveis",
                                "Não foi possível enviar as faixas indisponíveis:\n" + "\n".join(missing))
        if paths:
            try:
                self.send_to_phone(paths)
            except ShareError as exc:
                QMessageBox.warning(self.table, "Enviar para o celular", str(exc))

    def delete_selected(self):
        tracks = self.selected_tracks()
        if not tracks or self.delete_tracks is None:
            return
        count = len({track.id for track in tracks if track.id is not None})
        if not count:
            return
        answer = QMessageBox.question(self.table, "Excluir faixas",
                                      f"Enviar {count} faixa(s) para a Lixeira e removê-las da biblioteca?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed, errors = self.delete_tracks([track.id for track in tracks if track.id is not None])
        if self.refresh_library:
            self.refresh_library()
        if errors:
            QMessageBox.warning(self.table, "Falha ao excluir", "\n".join(
                f"{track.title}: {message}" for track, message in errors))

    def open_menu(self, position):
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        if not self.table.selectionModel().isRowSelected(index.row(), index.parent()):
            self.table.selectRow(index.row())
        menu = self.make_menu()
        menu.exec(self.table.viewport().mapToGlobal(position))
        menu.deleteLater()
