"""Interfaces que os casos de uso esperam; a camada infrastructure as implementa."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ytdown.domain.library import AlbumSummary, ArtistSummary, GenreSummary, Track, TrackQuery
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


class TrackRepository(Protocol):
    """Índice persistente da biblioteca.

    Os resultados de `list_tracks`, `artists`, `albums` e `genres` devem ser iguais aos das
    funções de referência em `ytdown.domain.library` (query_tracks, summarize_*). O teste
    de contrato em `tests/contracts/track_repository.py` verifica isso em cada implementação.
    """

    def add(self, track: Track) -> Track:
        """Salva uma faixa nova e a devolve com o `id` preenchido."""

    def update(self, track: Track) -> None:
        """Substitui todos os dados da faixa com o mesmo `id`. Falha com KeyError se ela não existir."""

    def remove(self, track_id: int) -> None:
        """Remove a faixa; não faz nada se ela não existir."""

    def get(self, track_id: int) -> Track | None: ...

    def find_by_source_url(self, url: str) -> Track | None: ...

    def find_by_path(self, rel_path: str) -> Track | None: ...

    def list_tracks(self, query: TrackQuery = TrackQuery()) -> list[Track]: ...

    def artists(self) -> list[ArtistSummary]: ...

    def albums(self, artist: str | None = None) -> list[AlbumSummary]:
        """Todos os álbuns ou, com `artist` (nome de exibição), só os desse artista."""

    def genres(self) -> list[GenreSummary]: ...


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
