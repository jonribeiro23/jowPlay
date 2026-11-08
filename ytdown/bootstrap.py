"""Ponto de montagem: escolhe as implementações concretas e as entrega a quem usa."""

from __future__ import annotations

import ctypes
import tkinter as tk
from collections.abc import Callable

from ytdown.application.extraction import ExtractAudio, ExtractBatch
from ytdown.application.sharing import SharingSession
from ytdown.infrastructure.covers import PillowCoverLoader
from ytdown.infrastructure.resources import asset
from ytdown.infrastructure.sharing.device_store import JsonDeviceStore, default_store_path
from ytdown.infrastructure.sharing.server import LocalShareServer
from ytdown.infrastructure.tags import MutagenTagWriter
from ytdown.infrastructure.youtube import YtDlpDownloader
from ytdown.presentation.main_window import MainWindow


def build_extract_batch() -> ExtractBatch:
    covers = PillowCoverLoader(default_cover=asset("default_cover.jpg"))
    extract = ExtractAudio(YtDlpDownloader(), covers, MutagenTagWriter())
    return ExtractBatch(extract, covers)


def create_share_server(on_change: Callable[[], None]) -> LocalShareServer:
    session = SharingSession(JsonDeviceStore(default_store_path()), on_change)
    return LocalShareServer(session)


def run() -> None:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Evita texto borrado em telas com escala.
    root = tk.Tk()
    root.iconbitmap(default=str(asset("icon.ico")))  # Vale também para as outras janelas.
    MainWindow(root, build_extract_batch(), create_share_server)
    root.update_idletasks()
    root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
    root.mainloop()
