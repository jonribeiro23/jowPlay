"""Painel da fila, ligado ao Playback pela posição de cada entrada."""
from __future__ import annotations

import weakref

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout, QWidget, QMenu, QMessageBox)

from ytdown.presentation.qt import theme
from ytdown.presentation.qt.songs_page import TRACKS_MIME, SongsTable
from ytdown.presentation.qt.transport_bar import _time

TITLE = "Lista de reprodução"
EMPTY_MESSAGE = "A lista de reprodução está vazia."


class _Listener:
    def __init__(self, pane):
        self.pane = weakref.ref(pane)

    def on_queue_changed(self):
        pane = self.pane()
        if pane is not None:
            pane.refresh()

    def on_track_changed(self, track):
        self.on_queue_changed()

    def on_state_changed(self, state): pass
    def on_position_changed(self, position, duration): pass
    def on_track_unavailable(self, track, message): pass


class _QueueList(QListWidget):
    def __init__(self, pane):
        super().__init__(pane)
        self.pane = pane
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.source() is self or (isinstance(event.source(), SongsTable) and event.mimeData().hasFormat(TRACKS_MIME)):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is self or (isinstance(event.source(), SongsTable) and event.mimeData().hasFormat(TRACKS_MIME)):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.pane._playback is None:
            event.ignore()
            return
        if isinstance(event.source(), SongsTable) and event.mimeData().hasFormat(TRACKS_MIME):
            source = event.source()
            rows = sorted(index.row() for index in source.selectionModel().selectedRows())
            self.pane._playback.append([source.model().tracks[row] for row in rows])
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        elif event.source() is self:
            rows = sorted(self.row(item) for item in self.selectedItems())
            if len(rows) != 1:
                event.ignore()
                return
            target_item = self.itemAt(event.position().toPoint())
            target = self.row(target_item) if target_item else self.count()
            if target_item and event.position().y() > self.visualItemRect(target_item).center().y():
                target += 1
            source = rows[0]
            target -= target > source
            if target != source:
                self.pane._playback.move(source, target)
                self.setCurrentRow(target)
            # A lista foi reconstruída pelo Playback; o Qt não deve remover a origem.
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.pane._playback is not None:
            if self.pane.delete_tracks is not None:
                self.pane.delete_selected()
                event.accept()
                return
            for row in sorted((self.row(item) for item in self.selectedItems()), reverse=True):
                self.pane._playback.remove(row)
            event.accept()
            return
        super().keyPressEvent(event)


class PlayQueuePane(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._playback = None
        self.delete_tracks = None
        self.refresh_library = None
        self._keys = []
        self.setObjectName("playQueuePane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setMinimumWidth(200)
        title = QLabel(TITLE)
        title.setObjectName("paneTitle")
        self.items = _QueueList(self)
        self.items.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.items.customContextMenuRequested.connect(self._menu)
        self.items.setObjectName("playQueue")
        self.empty_message = QLabel(EMPTY_MESSAGE)
        self.empty_message.setObjectName("paneHint")
        self.empty_message.setWordWrap(True)
        self.total = QLabel("0 faixas · 0:00")
        self.clear_button = QPushButton("Limpar")
        self.clear_button.setEnabled(False)
        self.save_button = QPushButton("Salvar playlist")
        self.save_button.setEnabled(False)
        self.save_button.setToolTip("Salvar playlists estará disponível futuramente.")
        buttons = QHBoxLayout()
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[theme.PANE_MARGIN] * 4)
        layout.addWidget(title)
        layout.addWidget(self.empty_message)
        layout.addWidget(self.items, stretch=1)
        layout.addWidget(self.total)
        layout.addLayout(buttons)

    def bind(self, playback):
        if self._playback is not None:
            raise RuntimeError("Painel já ligado ao Playback")
        self._playback = playback
        listener = _Listener(self)
        self._listener = listener
        playback.add_listener(listener)
        self.destroyed.connect(lambda: playback.remove_listener(listener))
        self.clear_button.clicked.connect(playback.clear)
        self.items.itemDoubleClicked.connect(lambda item: playback.select(self.items.row(item)))
        self.refresh()

    def shutdown(self):
        if self._playback is not None:
            self._playback.remove_listener(self._listener)

    def _menu(self, position):
        item = self.items.itemAt(position)
        if item is None or self.delete_tracks is None:
            return
        if not item.isSelected():
            self.items.setCurrentItem(item)
        menu = QMenu(self.items)
        menu.addAction("Remover da fila", self.remove_selected)
        menu.addAction("Excluir da biblioteca", self.delete_selected)
        menu.exec(self.items.viewport().mapToGlobal(position))
        menu.deleteLater()

    def remove_selected(self):
        for row in sorted((self.items.row(item) for item in self.items.selectedItems()), reverse=True):
            self._playback.remove(row)

    def delete_selected(self):
        ids = {self._playback.queue[self.items.row(item)].id for item in self.items.selectedItems()}
        ids.discard(None)
        if not ids:
            return
        answer = QMessageBox.question(self, "Excluir faixas",
                                      f"Enviar {len(ids)} faixa(s) para a Lixeira e removê-las da biblioteca?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        _, errors = self.delete_tracks(ids)
        if self.refresh_library:
            self.refresh_library()
        if errors:
            QMessageBox.warning(self, "Falha ao excluir", "\n".join(
                f"{track.title}: {message}" for track, message in errors))

    def refresh(self):
        if self._playback is None:
            return
        selected = {self._keys[self.items.row(item)] for item in self.items.selectedItems()}
        current_row = self.items.currentRow()
        current_key = self._keys[current_row] if 0 <= current_row < len(self._keys) else None
        tracks = self._playback.queue
        self._keys = self._playback.queue_entry_keys
        self.items.clear()
        for row, track in enumerate(tracks):
            item = QListWidgetItem(f"{track.title} — {track.display_artist}  {_time(track.duration_ms)}")
            item.setToolTip(item.text())
            font = item.font()
            font.setBold(row == self._playback.current_index)
            item.setFont(font)
            self.items.addItem(item)
        if current_key in self._keys:
            self.items.setCurrentRow(self._keys.index(current_key), QItemSelectionModel.SelectionFlag.NoUpdate)
        for row, key in enumerate(self._keys):
            if key in selected:
                self.items.item(row).setSelected(True)
        self.empty_message.setVisible(not tracks)
        self.clear_button.setEnabled(bool(tracks))
        self.total.setText(f"{len(tracks)} faixas · {_time(sum(max(0, t.duration_ms) for t in tracks))}")
