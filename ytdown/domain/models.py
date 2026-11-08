"""Conceitos centrais: formatos de áudio, metadados, progresso e resultados."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


@dataclass(frozen=True)
class AudioFormat:
    label: str
    codec: str
    extension: str
    bitrate: str | None = None


AUDIO_FORMATS = (
    AudioFormat("MP3 - 192 kbps (recomendado)", "mp3", "mp3", "192"),
    AudioFormat("MP3 - 320 kbps", "mp3", "mp3", "320"),
    AudioFormat("MP3 - 128 kbps (arquivo menor)", "mp3", "mp3", "128"),
    AudioFormat("M4A (AAC) - 192 kbps", "m4a", "m4a", "192"),
    AudioFormat("FLAC (sem perda adicional)", "flac", "flac"),
    AudioFormat("WAV (sem compressão)", "wav", "wav"),
)


@dataclass(frozen=True)
class AudioMetadata:
    """Dados escolhidos pelo usuário. Vazio significa usar o valor padrão."""

    title: str = ""  # Padrão: título do vídeo.
    artist: str = ""  # Padrão: sem artista.
    cover: Path | None = None  # Padrão: a capa padrão do app.
    album: str = ""
    genre: str = ""
    year: int | None = None
    track_no: int | None = None


@dataclass(frozen=True)
class AudioFileInfo:
    """O que se sabe de um arquivo de áudio existente. Etiqueta ausente vira None."""

    duration_ms: int
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    year: int | None = None
    track_no: int | None = None
    source_url: str | None = None
    has_cover: bool = False


@dataclass(frozen=True)
class AudioTags:
    """Tudo o que é gravado nas etiquetas de um arquivo de áudio.

    Campos vazios (texto vazio, None ou zero) não são gravados, e removem a
    etiqueta correspondente se ela já existir no arquivo.
    """

    title: str
    cover: bytes  # JPEG.
    artist: str = ""
    album: str = ""
    genre: str = ""
    year: int | None = None
    track_no: int | None = None
    source_url: str | None = None  # Página do vídeo de origem; identifica duplicatas.


class Stage(Enum):
    STARTING = auto()
    FETCHING_INFO = auto()
    DOWNLOADING = auto()
    CONVERTING = auto()
    TAGGING = auto()
    SAVING = auto()


@dataclass(frozen=True)
class Progress:
    stage: Stage
    percent: float | None = None  # Só no download, quando o tamanho total é conhecido.


@dataclass(frozen=True)
class BatchResult:
    """Resultado de um vídeo da fila: salvo (`path`), com falha (`error`) ou cancelado."""

    url: str
    path: Path | None = None
    error: str | None = None
    cancelled: bool = False
