"""Ponto de montagem: escolhe as implementações concretas e as entrega a quem usa."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ytdown.application.extraction import ExtractAudio, ExtractBatch
from ytdown.application.library import ChangeLibraryFolder, RegisterExtractedTrack, library_folder
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
    )


def create_share_server(on_change: Callable[[], None]) -> LocalShareServer:
    session = SharingSession(JsonDeviceStore(default_store_path()), on_change)
    return LocalShareServer(session)


def run() -> int:
    """Abre a nova interface em Qt (ytDown 2.0, em construção)."""
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ytdown.domain.errors import LibraryError
    from ytdown.presentation.qt.extract_page import ExtractPage
    from ytdown.presentation.qt.main_window import MainWindow
    from ytdown.presentation.qt.options_dialog import OptionsDialog
    from ytdown.presentation.qt.pages import PageId, PlaceholderPage
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
    extract_batch = build_extract_batch()
    sharing = PhoneSharing(create_share_server)
    pages = {}

    def page_factory(page: PageId):
        if page is PageId.EXTRACT:
            pages[page] = ExtractPage(extract_batch, library.register, send_to_phone=sharing.send)
        else:
            pages[page] = PlaceholderPage(page)
        return pages[page]

    window = MainWindow(page_factory)
    sharing.parent = window  # A janela de envio fica à frente da principal e sai junto com ela.

    def open_options() -> None:
        extract_page = pages[PageId.EXTRACT]
        dialog = OptionsDialog(lambda: library.register.folder, library.change_folder, extract_page.is_working,
                               window)
        dialog.finished.connect(extract_page.refresh_library_folder)
        dialog.open()

    window.options_requested.connect(open_options)
    window.show()
    exit_code = app.exec()
    sharing.stop()  # O app pode sair com a janela de envio aberta; o servidor não pode continuar.
    # Apaga a janela enquanto a QApplication ainda existe; deixar para o fim do processo
    # faz o Python destruí-las em ordem qualquer, e o app pode cair ao fechar.
    del window, pages
    library.close()
    return exit_code


def run_legacy() -> None:
    """Interface Tkinter da versão 1.x, mantida até a JOW-21."""
    import tkinter as tk

    from ytdown.presentation.main_window import MainWindow

    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Evita texto borrado em telas com escala.
    root = tk.Tk()
    root.iconbitmap(default=str(asset("icon.ico")))  # Vale também para as outras janelas.
    MainWindow(root, build_extract_batch(), create_share_server)
    root.update_idletasks()
    root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
    root.mainloop()
