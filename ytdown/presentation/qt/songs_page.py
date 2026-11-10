"""Lista virtualizada da biblioteca, com ordenação delegada ao repositório."""
from dataclasses import replace
from PySide6.QtCore import QAbstractTableModel, QByteArray, QMimeData, QModelIndex, Qt, Signal
from PySide6.QtGui import QDrag, QPalette
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHBoxLayout, QLabel, QMenu, QPushButton, QTableView, QVBoxLayout, QWidget

from ytdown.application.ports import Settings, TrackRepository
from ytdown.application.playback import Playback
from ytdown.domain.library import SortField, TrackQuery
from ytdown.presentation.qt import theme
from ytdown.presentation.qt.track_actions import TrackActions
from ytdown.presentation import texts

COLUMNS = (
    ("Título", SortField.TITLE), ("Artista", SortField.ARTIST),
    ("Álbum", SortField.ALBUM), ("Duração", SortField.DURATION),
    ("Gênero", SortField.GENRE), ("Ano", SortField.YEAR),
    ("Nº", SortField.TRACK_NO), ("Adicionada em", SortField.ADDED_AT),
    ("Reproduções", SortField.PLAY_COUNT), ("Última reprodução", SortField.LAST_PLAYED),
)
HEADER_KEY = "songs.header"
TRACKS_MIME = "application/x-ytdown-tracks"


class SongsTable(QTableView):
    def startDrag(self, supported_actions):
        if not self.selectionModel().selectedRows():
            return
        mime = QMimeData()
        mime.setData(TRACKS_MIME, QByteArray(b"tracks"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class TrackTableModel(QAbstractTableModel):
    def __init__(self, repository: TrackRepository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.query = TrackQuery(sort=SortField.TITLE)
        self.tracks = []
        self.ids = None
        self.refresh()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.tracks)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section][0]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.tracks) or not 0 <= index.column() < len(COLUMNS):
            return None
        track = self.tracks[index.row()]
        if role == Qt.ItemDataRole.ForegroundRole and track.missing:
            return QApplication.palette().brush(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
        if role == Qt.ItemDataRole.ToolTipRole and track.missing:
            return "Arquivo indisponível"
        if role == Qt.ItemDataRole.DisplayRole:
            seconds = track.duration_ms // 1000
            duration = f"{seconds // 60}:{seconds % 60:02d}"
            return (track.title, track.display_artist, track.display_album, duration,
                    track.display_genre, track.year if track.year is not None else "",
                    track.track_no if track.track_no is not None else "",
                    track.added_at.strftime("%d/%m/%Y %H:%M"), track.play_count,
                    track.last_played_at.strftime("%d/%m/%Y %H:%M") if track.last_played_at else "")[index.column()]
        return None

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if 0 <= column < len(COLUMNS):
            self.query = replace(self.query, sort=COLUMNS[column][1], descending=order == Qt.SortOrder.DescendingOrder)
            self.refresh()

    def set_search_text(self, text):
        if text != self.query.text:
            self.query = replace(self.query, text=text)
            self.refresh()

    def refresh(self):
        tracks = self.repository.list_tracks(self.query)
        if self.ids is not None:
            tracks = [track for track in tracks if track.id in self.ids]
        self.beginResetModel()
        self.tracks = tracks
        self.endResetModel()

    def set_ids(self, ids):
        self.ids = None if ids is None else set(ids)
        self.refresh()


class SongsPage(QWidget):
    """A tabela tem seu próprio viewport: nunca cresce com o número de faixas."""
    library_refreshed = Signal()

    def __init__(self, repository: TrackRepository, playback: Playback, settings: Settings,
                 remove_unavailable=None, storage=None, title="Músicas", send_to_phone=None):
        super().__init__()
        self.setObjectName("page-songs")
        self.playback, self.settings = playback, settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[theme.PAGE_MARGIN] * 4)
        heading = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        heading.addWidget(title_label)
        heading.addStretch()
        self.remove_unavailable_button = QPushButton("Remover faixas indisponíveis")
        self.remove_unavailable_button.setToolTip("Remove somente os registros de arquivos que continuam ausentes.")
        self._remove_unavailable = remove_unavailable
        self.remove_unavailable_button.clicked.connect(self.remove_unavailable)
        heading.addWidget(self.remove_unavailable_button)
        layout.addLayout(heading)
        self.table = SongsTable()
        self.model = TrackTableModel(repository, self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.track_actions = TrackActions(self.table, playback, storage, send_to_phone)
        self.table.setDragEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self.table.setSortingEnabled(True)
        saved = settings.get(HEADER_KEY)
        if isinstance(saved, str):
            header.restoreState(QByteArray.fromBase64(saved.encode("ascii", errors="ignore")))
        self.model.sort(header.sortIndicatorSection(), header.sortIndicatorOrder())
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._column_menu)
        header.sectionMoved.connect(self.save_preferences)
        header.sectionResized.connect(self.save_preferences)
        header.sortIndicatorChanged.connect(self.save_preferences)
        self.model.modelAboutToBeReset.connect(self._remember_selection)
        self.model.modelReset.connect(self._restore_selection)
        self._selected_ids = set()
        self._current_id = None
        self.table.activated.connect(self.play_index)
        layout.addWidget(self.table, 1)
        self.count = QLabel()
        layout.addWidget(self.count)
        self._update_count()
        listener = _PlayRecordedListener(self)
        playback.add_listener(listener)
        self.destroyed.connect(lambda: playback.remove_listener(listener))

    def save_preferences(self, *args):
        self.settings.set(HEADER_KEY, bytes(self.table.horizontalHeader().saveState().toBase64()).decode("ascii"))

    def set_column_visible(self, column, visible):
        self.table.setColumnHidden(column, not visible)
        self.save_preferences()

    def _column_menu(self, position):
        menu = QMenu(self)
        for column, (label, _) in enumerate(COLUMNS):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(column))
            action.toggled.connect(lambda visible, column=column: self.set_column_visible(column, visible))
        menu.exec(self.table.horizontalHeader().mapToGlobal(position))
        menu.deleteLater()

    def play_index(self, index):
        if index.isValid():
            self.playback.play_tracks(self.model.tracks, index.row())

    def _remember_selection(self):
        visible_ids = {track.id for track in self.model.tracks}
        self._selected_ids.difference_update(visible_ids)
        self._selected_ids.update(self.model.tracks[i.row()].id for i in self.table.selectionModel().selectedRows())
        current = self.table.currentIndex()
        if current.isValid():
            self._current_id = self.model.tracks[current.row()].id
        elif self._current_id in visible_ids:
            self._current_id = None

    def _restore_selection(self):
        from PySide6.QtCore import QItemSelection, QItemSelectionModel
        selection = QItemSelection()
        for row, track in enumerate(self.model.tracks):
            if track.id in self._selected_ids:
                selection.select(self.model.index(row, 0), self.model.index(row, len(COLUMNS) - 1))
            if track.id == self._current_id:
                self.table.selectionModel().setCurrentIndex(self.model.index(row, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
        self.table.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.Select)
        self._update_count()

    def refresh(self):
        self.model.refresh()
        self.library_refreshed.emit()

    def set_search_text(self, text):
        self.model.set_search_text(text)

    def set_ids(self, ids):
        self.model.set_ids(ids)

    def remove_unavailable(self) -> None:
        if self._remove_unavailable is None:
            return
        removed = self._remove_unavailable()
        self.playback.remove_tracks(removed)
        self.refresh()

    def _update_count(self):
        missing = sum(track.missing for track in self.model.tracks)
        self.count.setText(texts.tracks_count(self.model.rowCount()))
        self.remove_unavailable_button.setEnabled(bool(missing) and self._remove_unavailable is not None)


class _PlayRecordedListener:
    def __init__(self, page):
        self.page = page

    def on_play_recorded(self, track):
        self.page.refresh()

    def on_track_changed(self, track): pass
    def on_state_changed(self, state): pass
    def on_position_changed(self, position_ms, duration_ms): pass
    def on_queue_changed(self): pass
    def on_track_unavailable(self, track, message): pass
