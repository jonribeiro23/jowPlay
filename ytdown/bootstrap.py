"""Ponto de montagem: escolhe as implementações concretas e as entrega a quem usa."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ytdown.application.playback import Playback
from ytdown.application.ports import Settings, LibraryStorage
from ytdown.application.extraction import ExtractAudio, ExtractBatch
from ytdown.application.library import ChangeLibraryFolder, RegisterExtractedTrack, known_genres, library_folder
from ytdown.application.sharing import SharingSession
from ytdown.infrastructure.covers import PillowCoverLoader
from ytdown.infrastructure.json_settings import JsonSettings, default_settings_path
from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
from ytdown.infrastructure.metadata_reader import MutagenMetadataReader
from ytdown.infrastructure.thumbnails import FileThumbnailCache
from ytdown.infrastructure.resources import asset
from ytdown.infrastructure.sharing.device_store import JsonDeviceStore, default_store_path
from ytdown.infrastructure.sharing.server import LocalShareServer
from ytdown.infrastructure.sqlite_library import SqliteTrackRepository, default_library_db_path
from ytdown.infrastructure.tags import MutagenTagWriter
from ytdown.infrastructure.windows_shell import music_folder
from ytdown.infrastructure.youtube import YtDlpDownloader

APP_ID = "ytDown.Player"  # Agrupa as janelas do app na barra de tarefas, com o ícone certo.
LIBRARY_FOLDER_NAME = "ytDown"  # Dentro da pasta Música do usuário.


def build_extract_batch() -> ExtractBatch:
    covers = PillowCoverLoader(default_cover=asset("default_cover.jpg"))
    extract = ExtractAudio(YtDlpDownloader(), covers, MutagenTagWriter())
    return ExtractBatch(extract, covers)


@dataclass
class Library:
    register: RegisterExtractedTrack
    change_folder: ChangeLibraryFolder
    tracks: SqliteTrackRepository
    settings: Settings
    storage: LibraryStorage
    thumbnails: FileThumbnailCache

    def close(self) -> None:
        self.thumbnails.close()
        self.tracks.close()


def build_library(db_path: Path | None = None, settings_path: Path | None = None,
                  default_folder: Path | None = None) -> Library:
    """A biblioteca real. Os caminhos só mudam nos testes. Falha com LibraryError."""
    settings = JsonSettings(settings_path or default_settings_path())
    storage = FileSystemLibraryStorage(library_folder(settings, default_folder or music_folder() / LIBRARY_FOLDER_NAME))
    tracks = SqliteTrackRepository(db_path or default_library_db_path())
    thumbnails = FileThumbnailCache(MutagenMetadataReader())
    return Library(
        register=RegisterExtractedTrack(storage, tracks, MutagenMetadataReader(), thumbnails=thumbnails),
        change_folder=ChangeLibraryFolder(storage, tracks, settings),
        tracks=tracks,
        settings=settings,
        storage=storage,
        thumbnails=thumbnails,
    )


def create_share_server(on_change: Callable[[], None]) -> LocalShareServer:
    session = SharingSession(JsonDeviceStore(default_store_path()), on_change)
    return LocalShareServer(session)


def run() -> int:
    """Abre o app (interface em Qt) e devolve o código de saída."""
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ytdown.domain.errors import LibraryError
    from ytdown.infrastructure.qt_audio_player import QtAudioPlayer
    from ytdown.presentation.qt.send_dialog import PhoneSharing
    from ytdown.presentation.qt.theme import apply_theme

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    app = QApplication(sys.argv)
    app.setApplicationName("ytDown")
    app.setWindowIcon(QIcon(str(asset("icon.ico"))))
    apply_theme(app, asset("theme"))
    try:
        library = build_library()
    except LibraryError as exc:  # Ex.: biblioteca criada por uma versão mais nova do app.
        QMessageBox.critical(None, "ytDown", str(exc))
        return 1
    player = QtAudioPlayer(app)
    playback = Playback(player, library.storage, tracks=library.tracks)
    extract_batch = build_extract_batch()
    sharing = PhoneSharing(create_share_server)
    window = build_main_window(library, playback, extract_batch, sharing)
    start_library_check(window, library)
    window.closing.connect(player.shutdown)
    window.show()
    exit_code = app.exec()
    playback.stop()
    player.shutdown()
    sharing.stop()  # O app pode sair com a janela de envio aberta; o servidor não pode continuar.
    # Apaga a janela enquanto a QApplication ainda existe; deixar para o fim do processo
    # faz o Python destruí-las em ordem qualquer, e o app pode cair ao fechar.
    del window
    library.close()
    return exit_code


def build_main_window(library, playback, extract_batch, sharing):
    """Monta a janela com os mesmos servicos compartilhados, inclusive nos testes offscreen."""
    from ytdown.presentation.qt.extract_page import ExtractPage
    from ytdown.presentation.qt.main_window import MainWindow
    from ytdown.presentation.qt.options_dialog import OptionsDialog
    from ytdown.presentation.qt.pages import PageId, PlaceholderPage
    from ytdown.presentation.qt.songs_page import SongsPage
    from ytdown.presentation.qt.albums_page import AlbumsPage
    from ytdown.presentation.qt.groups_page import GroupsPage
    from ytdown.presentation.qt.now_playing import NowPlayingPage, CompactPlayer
    from PySide6.QtGui import QPixmap
    from ytdown.application.library import DeleteTracks, RemoveUnavailableTracks

    from ytdown.application.importing import ImportAudios
    from ytdown.infrastructure.import_files import FileSystemImportFiles
    from ytdown.presentation.qt.import_dialog import ImportDialog

    pages = {}
    def read_cover(track):
        path = library.thumbnails.get_or_create(library.storage.absolute(track.rel_path))
        return path.read_bytes() if path else None

    remove_unavailable_case = RemoveUnavailableTracks(library.storage, library.tracks)

    def page_factory(page: PageId):
        if page is PageId.NOW_PLAYING:
            pages[page] = NowPlayingPage(playback, read_cover, QPixmap(str(asset("default_cover.jpg"))))
        elif page in (PageId.SONGS, PageId.RECENT):
            pages[page] = SongsPage(library.tracks, playback, library.settings, storage=library.storage,
                                    title=page.title)
            if page is PageId.RECENT:
                pages[page].set_ids([])
        elif page is PageId.ALBUMS:
            pages[page] = AlbumsPage(library.tracks, playback, library.storage, library.thumbnails,
                                     asset("default_cover.jpg"))
        elif page in (PageId.ARTISTS, PageId.GENRES):
            pages[page] = GroupsPage(library.tracks, playback, "artist" if page is PageId.ARTISTS else "genre",
                                     storage=library.storage)
        elif page is PageId.EXTRACT:
            pages[page] = ExtractPage(extract_batch, library.register, send_to_phone=sharing.send,
                                      genre_suggestions=lambda: known_genres(library.tracks))
        else:
            pages[page] = PlaceholderPage(page)
        return pages[page]

    window = MainWindow(page_factory, settings=library.settings)
    from ytdown.presentation.qt.playback_shortcuts import PlaybackShortcuts
    window.playback_shortcuts = PlaybackShortcuts(window, playback)
    window.closing.connect(window.playback_shortcuts.shutdown)
    window.compact_player = CompactPlayer(playback, pages[PageId.NOW_PLAYING], library.settings, window)
    pages[PageId.NOW_PLAYING].compact_requested.connect(window.compact_player.show)
    window.closing.connect(window.compact_player.shutdown)
    window.navigation.set_counts(library.tracks)
    pages[PageId.SONGS].model.modelReset.connect(lambda: window.navigation.set_counts(library.tracks))
    pages[PageId.SONGS].model.modelReset.connect(pages[PageId.ALBUMS].refresh)
    for group_page in (PageId.ARTISTS, PageId.GENRES):
        pages[PageId.SONGS].model.modelReset.connect(pages[group_page].refresh)
        pages[group_page].detail_changed.connect(
            lambda title, page=group_page: window.breadcrumb.setText(
                "Biblioteca › " + page.title + (" › " + title if title else ""))
            if window.current_page() is page else None)
    pages[PageId.ALBUMS].detail_changed.connect(
        lambda title: window.breadcrumb.setText("Biblioteca › Álbuns" + (" › " + title if title else ""))
        if window.current_page() is PageId.ALBUMS else None)
    window.play_queue.bind(playback)
    window.closing.connect(window.play_queue.shutdown)
    from PySide6.QtGui import QPixmap

    window.transport.bind(
        playback,
        read_cover=read_cover,
        default_cover=QPixmap(str(asset("default_cover.jpg"))),
    )
    playback.restore_workspace(library.settings.get("workspace.playback"), library.tracks)
    window.closing.connect(lambda: library.settings.set("workspace.playback", playback.workspace_state()))
    pages[PageId.EXTRACT].extraction_finished.connect(pages[PageId.SONGS].refresh)
    pages[PageId.SONGS].model.modelReset.connect(pages[PageId.RECENT].refresh)
    delete_tracks = DeleteTracks(library.storage, library.tracks, playback)
    for page in (PageId.SONGS, PageId.RECENT, PageId.ALBUMS, PageId.ARTISTS, PageId.GENRES):
        pages[page].track_actions.delete_tracks = delete_tracks
        pages[page].track_actions.refresh_library = pages[PageId.SONGS].refresh
    window.play_queue.delete_tracks = delete_tracks
    window.play_queue.refresh_library = pages[PageId.SONGS].refresh
    last_ids = []
    session_ids = set()

    def extraction_results(paths):
        last_ids.clear()
        for path in paths:
            try:
                relative = path.relative_to(library.storage.root).as_posix()
            except ValueError:
                continue
            track = library.tracks.find_by_path(relative)
            if track is not None:
                last_ids.append(track.id)
                session_ids.add(track.id)
        pages[PageId.RECENT].set_ids(session_ids)
        pages[PageId.EXTRACT].play_button.setEnabled(bool(last_ids))
        pages[PageId.EXTRACT].library_button.setEnabled(bool(last_ids))

    def play_extracted():
        tracks = [track for track_id in last_ids if (track := library.tracks.get(track_id)) is not None]
        if tracks:
            playback.play_tracks(tracks, 0)

    def view_extracted():
        window.search.clear()
        pages[PageId.SONGS].set_ids(last_ids)
        window.show_page(PageId.SONGS)

    pages[PageId.EXTRACT].results_ready.connect(extraction_results)
    pages[PageId.EXTRACT].play_requested.connect(play_extracted)
    pages[PageId.EXTRACT].library_requested.connect(view_extracted)
    window.navigation.page_selected.connect(lambda page: pages[PageId.SONGS].set_ids(None)
                                            if page is PageId.SONGS else None)
    window.navigation.itemClicked.connect(lambda item, column: pages[PageId.SONGS].set_ids(None)
                                          if item is window.navigation._items[PageId.SONGS] else None)
    sharing.parent = window  # A janela de envio fica à frente da principal e sai junto com ela.

    window.background_dialogs = []
    window.background_jobs = []
    def importing():
        return any(d.is_working() for d in window.background_dialogs)

    pages[PageId.EXTRACT].external_busy = lambda: importing() or checking()

    def open_import():
        if pages[PageId.EXTRACT].is_working() or importing() or checking():
            return
        dialog = ImportDialog(ImportAudios(library.storage, library.tracks, MutagenMetadataReader(),
                              FileSystemImportFiles(), library.thumbnails), pages[PageId.EXTRACT].is_working, window)
        window.background_dialogs.append(dialog)
        dialog.import_finished.connect(pages[PageId.SONGS].refresh)
        dialog.finished.connect(lambda: window.background_dialogs.remove(dialog))
        dialog.open()

    window.import_requested.connect(open_import)

    def open_options() -> None:
        if importing() or checking():
            return
        extract_page = pages[PageId.EXTRACT]
        dialog = OptionsDialog(lambda: library.register.folder, library.change_folder,
                               lambda: extract_page.is_working() or importing() or checking(),
                               window)
        window.background_dialogs.append(dialog)
        dialog.finished.connect(lambda: window.background_dialogs.remove(dialog))
        dialog.finished.connect(extract_page.refresh_library_folder)
        dialog.open()

    window.options_requested.connect(open_options)
    window.closing.connect(playback.stop)

    def checking() -> bool:
        check = getattr(window, "library_check", None)
        return bool(check and check.is_working())

    def remove_unavailable():
        return set() if checking() else remove_unavailable_case()

    pages[PageId.SONGS]._remove_unavailable = remove_unavailable
    pages[PageId.SONGS]._update_count()

    return window


def start_library_check(window, library) -> None:
    """Começa depois de montar a janela; testes de composição não precisam criar uma thread."""
    from PySide6.QtWidgets import QMessageBox
    from ytdown.application.library import CheckLibrary
    from ytdown.presentation.qt.library_check import LibraryCheck
    from ytdown.presentation.qt.pages import PageId

    check = LibraryCheck(CheckLibrary(library.storage, library.tracks), window)
    window.library_check = check
    window.background_jobs.append(check)

    def checked(result) -> None:
        window.page(PageId.SONGS).refresh()
        if not result.root_available and result.indexed:
            QMessageBox.warning(window, "Biblioteca indisponível",
                                "A pasta da biblioteca não está disponível. Nenhuma faixa foi marcada como ausente.")

    check.finished.connect(checked)
    check.start()
