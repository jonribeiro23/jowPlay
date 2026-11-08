"""Leitura das etiquetas, da duração e da capa de arquivos de áudio com mutagen.

Lê as mesmas etiquetas que `tags.py` grava, e também as variações comuns gravadas
por outras ferramentas: ID3v2.4, ano como "2024-05-01" e faixa como "7/12".
"""

from __future__ import annotations

import re
from pathlib import Path

from mutagen import MutagenError
from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

from ytdown.domain.errors import UnreadableAudio
from ytdown.domain.models import AudioFileInfo
from ytdown.infrastructure.tags import MP4_SOURCE_KEY, PICTURE_TYPE_FRONT_COVER, VORBIS_SOURCE_KEY

_LEADING_NUMBER = re.compile(r"\s*(\d+)")


def _number(value) -> int | None:
    """Primeiro número do texto: "2024-05-01" vira 2024 e "7/12" vira 7. Zero ou nada vira None."""
    if value is None:
        return None
    match = _LEADING_NUMBER.match(str(value))
    number = int(match.group(1)) if match else 0
    return number or None


def _text(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _front_cover_first(pictures, kind):
    """Capa da frente, se houver; senão, a primeira imagem."""
    return next((p for p in pictures if kind(p) == PICTURE_TYPE_FRONT_COVER), pictures[0] if pictures else None)


# --- por formato: devolvem (campos, capa)


def _from_id3(id3: ID3 | None) -> tuple[dict, bytes | None]:
    if id3 is None:
        return {}, None

    def first(frame):
        return id3[frame].text[0] if frame in id3 and id3[frame].text else None

    woas = id3.getall("WOAS")
    pictures = id3.getall("APIC")
    cover = _front_cover_first(pictures, lambda p: p.type)
    fields = {
        "title": _text(first("TIT2")),
        "artist": _text(first("TPE1")),
        "album": _text(first("TALB")),
        "genre": _text(first("TCON")),
        "year": _number(first("TDRC")),  # O mutagen converte TYER (v2.3) em TDRC ao ler.
        "track_no": _number(first("TRCK")),
        "source_url": _text(woas[0].url) if woas else None,
    }
    return fields, cover.data if cover else None


def _read_mp3(path: Path):
    audio = MP3(path)
    try:
        id3 = ID3(path)
    except ID3NoHeaderError:
        id3 = None
    return audio.info.length, *_from_id3(id3)


def _read_wav(path: Path):
    audio = WAVE(path)
    return audio.info.length, *_from_id3(audio.tags)


def _read_m4a(path: Path):
    audio = MP4(path)
    tags = audio.tags or {}

    def first(key):
        values = tags.get(key)
        return values[0] if values else None

    source = first(MP4_SOURCE_KEY)
    track = first("trkn")
    covers = tags.get("covr") or []
    fields = {
        "title": _text(first("\xa9nam")),
        "artist": _text(first("\xa9ART")),
        "album": _text(first("\xa9alb")),
        "genre": _text(first("\xa9gen")),
        "year": _number(first("\xa9day")),
        "track_no": _number(track[0]) if track else None,
        "source_url": _text(bytes(source).decode("utf-8", "replace")) if source else None,
    }
    return audio.info.length, fields, bytes(covers[0]) if covers else None


def _read_flac(path: Path):
    audio = FLAC(path)

    def first(key):
        values = audio.get(key)
        return values[0] if values else None

    cover = _front_cover_first(audio.pictures, lambda p: p.type)
    fields = {
        "title": _text(first("title")),
        "artist": _text(first("artist")),
        "album": _text(first("album")),
        "genre": _text(first("genre")),
        "year": _number(first("date")),
        "track_no": _number(first("tracknumber")),
        "source_url": _text(first(VORBIS_SOURCE_KEY)),
    }
    return audio.info.length, fields, cover.data if cover else None


_READERS = {".mp3": _read_mp3, ".wav": _read_wav, ".m4a": _read_m4a, ".flac": _read_flac}


class MutagenMetadataReader:
    """Implementa MetadataReader para MP3, M4A, FLAC e WAV."""

    def read(self, path: Path) -> AudioFileInfo:
        length, fields, cover = self._read(path)
        return AudioFileInfo(duration_ms=round(length * 1000), has_cover=cover is not None, **fields)

    def read_cover(self, path: Path) -> bytes | None:
        return self._read(path)[2]

    @staticmethod
    def _read(path: Path):
        reader = _READERS.get(path.suffix.lower())
        if reader is None:
            raise UnreadableAudio(f"Formato sem suporte: {path.name}")
        try:
            return reader(path)
        except (MutagenError, OSError, ValueError) as exc:
            raise UnreadableAudio(f"Não foi possível ler o arquivo de áudio {path.name}: {exc}") from exc
