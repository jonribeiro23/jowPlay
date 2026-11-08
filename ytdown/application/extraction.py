"""Casos de uso de extração: um vídeo ou uma fila de vídeos."""

from __future__ import annotations

import tempfile
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from ytdown.application.ports import AudioDownloader, CoverLoader, DownloadedAudio, ProgressCallback, TagWriter
from ytdown.domain.errors import ExtractionCancelled, ExtractionError
from ytdown.domain.models import AudioFormat, AudioMetadata, AudioTags, BatchResult, Progress, Stage


def unique_path(path: Path) -> Path:
    """Devolve `path` ou, se já existir, `nome (1).ext`, `nome (2).ext`..."""
    candidate = path
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        counter += 1
    return candidate


class AudioDestination(Protocol):
    """Para onde vai o áudio pronto (já com as etiquetas)."""

    def save(self, file: Path, tags: AudioTags) -> Path:
        """Move `file` para o destino e devolve onde ele ficou. Falha com ExtractionError."""


class ExtractAudio:
    """Extrai o áudio de um vídeo, grava os metadados e entrega ao destino.

    Todo o trabalho acontece em uma pasta temporária, então uma falha ou um
    cancelamento nunca deixa arquivos pela metade no destino.
    """

    def __init__(self, downloader: AudioDownloader, covers: CoverLoader, tags: TagWriter) -> None:
        self._downloader = downloader
        self._covers = covers
        self._tags = tags

    def __call__(
        self,
        url: str,
        destination: AudioDestination,
        audio_format: AudioFormat,
        metadata: AudioMetadata,
        on_progress: ProgressCallback,
        cancel: threading.Event,
    ) -> Path:
        # Lê a capa antes de baixar: uma imagem inválida deve falhar logo no início.
        cover = self._covers.load(metadata.cover)

        with tempfile.TemporaryDirectory(prefix="ytdown-", ignore_cleanup_errors=True) as temp:
            audio = self._downloader.download(url, Path(temp), audio_format, on_progress, cancel)
            if cancel.is_set():
                raise ExtractionCancelled()

            on_progress(Progress(Stage.TAGGING))
            tags = self._tags_for(audio, metadata, cover)
            self._tags.write(audio.path, tags)

            on_progress(Progress(Stage.SAVING))
            return destination.save(audio.path, tags)

    @staticmethod
    def _tags_for(audio: DownloadedAudio, metadata: AudioMetadata, cover: bytes) -> AudioTags:
        return AudioTags(
            title=metadata.title or audio.title or audio.path.stem,
            cover=cover,
            artist=metadata.artist,
            album=metadata.album,
            genre=metadata.genre,
            year=metadata.year,
            track_no=metadata.track_no,
            source_url=audio.source_url,
        )


def video_metadata(metadata: AudioMetadata, index: int, total: int, number_tracks: bool = False) -> AudioMetadata:
    """Os dados de um vídeo da fila.

    Com um vídeo só, valem os dados escolhidos. Com vários, um mesmo nome ou nº de faixa
    para todos não faz sentido: cada um usa o título do próprio vídeo e, com `number_tracks`,
    o nº segue a ordem da lista, a partir do nº escolhido (ou de 1). Artista, álbum, gênero,
    ano e capa valem para todos.
    """
    if total == 1:
        return metadata
    track_no = (metadata.track_no or 1) + index if number_tracks else None
    return replace(metadata, title="", track_no=track_no)


class ExtractBatch:
    """Extrai vários vídeos, um de cada vez.

    Uma falha não interrompe os próximos; o cancelamento interrompe o vídeo atual
    e marca os restantes como cancelados.
    """

    def __init__(self, extract: ExtractAudio, covers: CoverLoader) -> None:
        self._extract = extract
        self._covers = covers

    def __call__(
        self,
        urls: list[str],
        destination: AudioDestination,
        audio_format: AudioFormat,
        metadata: AudioMetadata,
        on_progress: Callable[[int, Progress], None],
        on_result: Callable[[int, BatchResult], None],
        cancel: threading.Event,
        number_tracks: bool = False,
    ) -> list[BatchResult]:
        """`number_tracks`: numera as faixas na ordem da lista (ver `video_metadata`)."""
        # Uma capa inválida faria todos os vídeos falharem; melhor avisar uma vez só.
        self._covers.load(metadata.cover)

        results = []
        for index, url in enumerate(urls):
            own = video_metadata(metadata, index, len(urls), number_tracks)
            result = self._extract_one(index, url, destination, audio_format, own, on_progress, cancel)
            results.append(result)
            on_result(index, result)
        return results

    def _extract_one(self, index, url, destination, audio_format, metadata, on_progress, cancel) -> BatchResult:
        if cancel.is_set():
            return BatchResult(url, cancelled=True)
        try:
            path = self._extract(
                url, destination, audio_format, metadata, lambda progress: on_progress(index, progress), cancel
            )
            return BatchResult(url, path=path)
        except ExtractionCancelled:
            return BatchResult(url, cancelled=True)
        except ExtractionError as exc:
            return BatchResult(url, error=str(exc))
        except Exception as exc:  # Um erro inesperado em um vídeo não deve parar a fila.
            return BatchResult(url, error=f"Erro inesperado: {exc}")
