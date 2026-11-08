"""Interfaces que os casos de uso esperam; a camada infrastructure as implementa."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ytdown.domain.models import AudioFormat, Progress
from ytdown.domain.sharing import TransferStatus

ProgressCallback = Callable[[Progress], None]


@dataclass(frozen=True)
class DownloadedAudio:
    path: Path
    title: str | None  # Título do vídeo, se a fonte informar.


class AudioDownloader(Protocol):
    def download(
        self,
        url: str,
        work_dir: Path,
        audio_format: AudioFormat,
        on_progress: ProgressCallback,
        cancel: threading.Event,
    ) -> DownloadedAudio:
        """Baixa e converte o áudio dentro de `work_dir`.

        Falha com ExtractionError ou ExtractionCancelled.
        """


class CoverLoader(Protocol):
    def load(self, path: Path | None) -> bytes:
        """Devolve a capa pronta para gravar; sem `path`, a capa padrão. Falha com InvalidCover."""


class TagWriter(Protocol):
    def write(self, path: Path, title: str, author: str, cover: bytes) -> None:
        """Grava nome, autor (vazio remove) e capa no arquivo. Falha com ExtractionError."""


class DeviceRegistry(Protocol):
    """Identidade deste PC e celulares pareados, guardados entre execuções do app."""

    @property
    def server_id(self) -> str: ...

    def add_device(self, name: str) -> str:
        """Registra um celular e devolve o token que ele usará daqui em diante."""

    def knows(self, token: str) -> bool: ...


class ShareServer(Protocol):
    """O que a interface precisa do servidor que entrega os áudios ao celular."""

    @property
    def port(self) -> int: ...

    @property
    def pairing_code(self) -> str: ...

    def start(self) -> None:
        """Falha com ShareError."""

    def stop(self) -> None: ...

    def address(self) -> str: ...

    def share(self, path: Path) -> None: ...

    def statuses(self) -> list[tuple[str, TransferStatus]]: ...
