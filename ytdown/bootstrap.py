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

    def close(self) -> None:
        self.tracks.close()


def build_library(db_path: Path | None = None, settings_path: Path | None = None,
                  default_folder: Path | None = None) -> Library:
    """A biblioteca real. Os caminhos só mudam nos testes. Falha com LibraryError."""
    settings = JsonSettings(settings_path or default_settings_path())
    storage = FileSystemLibraryStorage(library_folder(settings, default_folder or music_folder() / LIBRARY_FOLDER_NAME))
    tracks = SqliteTrackRepository(db_path or default_library_db_path())
    return Library(
        register=RegisterExtractedTrack(storage, tracks, MutagenMetadataReader()),
        change_folder=ChangeLibraryFolder(storage, tracks, settings),
        tracks=tracks,
        settings=settings,
        storage=storage,
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

    from ytdown.application.importing import ImportAudios
    from ytdown.infrastructure.import_files import FileSystemImportFiles
    from ytdown.presentation.qt.import_dialog import ImportDialog

    pages = {}

    def page_factory(page: PageId):
        if page is PageId.SONGS:
            pages[page] = SongsPage(library.tracks, playback, library.settings)
        elif page is PageId.EXTRACT:
            pages[page] = ExtractPage(extract_batch, library.register, send_to_phone=sharing.send,
                                      genre_suggestions=lambda: known_genres(library.tracks))
        else:
            pages[page] = PlaceholderPage(page)
        return pages[page]

    window = MainWindow(page_factory)
    pages[PageId.EXTRACT].extraction_finished.connect(pages[PageId.SONGS].refresh)
    sharing.parent = window  # A janela de envio fica à frente da principal e sai junto com ela.

    window.background_dialogs = []
    def importing():
        return any(d.is_working() for d in window.background_dialogs)

    pages[PageId.EXTRACT].external_busy = importing

    def open_import():
        if pages[PageId.EXTRACT].is_working() or importing():
            return
        dialog = ImportDialog(ImportAudios(library.storage, library.tracks, MutagenMetadataReader(),
                              FileSystemImportFiles()), pages[PageId.EXTRACT].is_working, window)
        window.background_dialogs.append(dialog)
        dialog.import_finished.connect(pages[PageId.SONGS].refresh)
        dialog.finished.connect(lambda: window.background_dialogs.remove(dialog))
        dialog.open()

    window.import_requested.connect(open_import)

    def open_options() -> None:
        if importing():
            return
        extract_page = pages[PageId.EXTRACT]
        dialog = OptionsDialog(lambda: library.register.folder, library.change_folder, lambda: extract_page.is_working() or importing(),
                               window)
        window.background_dialogs.append(dialog)
        dialog.finished.connect(lambda: window.background_dialogs.remove(dialog))
        dialog.finished.connect(extract_page.refresh_library_folder)
        dialog.open()

    window.options_requested.connect(open_options)
    window.closing.connect(playback.stop)
    return window
