"""Ações comuns às tabelas de faixas da biblioteca."""
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QAbstractItemView, QMenu, QMessageBox

from ytdown.domain.errors import LibraryError, ShareError


def send_tracks_to_phone(parent, storage, send_to_phone, tracks):
    """Manda os arquivos das faixas ao diálogo de envio; as indisponíveis ficam de fora, com aviso."""
    paths, missing = [], []
    for track in tracks:
        try:
            path = storage.absolute(track.rel_path)
            if track.missing or not path.is_file():
                missing.append(track.title)
            else:
                paths.append(path)
        except (LibraryError, OSError):
            missing.append(track.title)
    if missing:
        QMessageBox.warning(parent, "Faixas indisponíveis",
                            "Não foi possível enviar as faixas indisponíveis:\n" + "\n".join(missing))
    if paths:
        try:
            send_to_phone(paths)
        except ShareError as exc:
            QMessageBox.warning(parent, "Enviar para o celular", str(exc))


class TrackActions:
    def __init__(self, table, playback, storage=None, send_to_phone=None):
        self.table, self.playback, self.storage = table, playback, storage
        self.send_to_phone = send_to_phone
        self.edit_properties = None
        self.cover_loader = None
        self.delete_tracks = None
        self.refresh_library = None
        self.playlist_navigation = None
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self.open_menu)
        self.shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), table)
        self.shortcut.activated.connect(self.delete_selected)
        self.properties_shortcut = QShortcut(QKeySequence("Alt+Return"), table)
        self.properties_shortcut.activated.connect(self.show_properties)
        self.properties_enter_shortcut = QShortcut(QKeySequence("Alt+Enter"), table)
        self.properties_enter_shortcut.activated.connect(self.show_properties)

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
        if self.edit_properties is not None:
            menu.addAction("Propriedades", self.show_properties)
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

    def show_properties(self):
        tracks = self.selected_tracks()
        if not tracks or self.edit_properties is None:
            return
        from PySide6.QtWidgets import QDialog
        from ytdown.presentation.qt.properties_dialog import PropertiesDialog
        dialog = PropertiesDialog(tracks, self.edit_properties, self.table, self.cover_loader)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            for track in dialog.tracks:
                self.playback.update_track(track)
            if dialog.tracks and self.refresh_library:
                self.refresh_library()

    def send_tracks(self, tracks):
        send_tracks_to_phone(self.table, self.storage, self.send_to_phone, tracks)

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
