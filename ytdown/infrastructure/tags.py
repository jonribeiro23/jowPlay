"""Gravação de nome, autor e capa nos arquivos de áudio com mutagen."""

from __future__ import annotations

import io
from pathlib import Path

from mutagen import MutagenError
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TIT2, TPE1, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE
from PIL import Image

from ytdown.domain.errors import ExtractionError

PICTURE_TYPE_FRONT_COVER = 3


def _apply_id3(tags: ID3, title: str, author: str, cover: bytes) -> None:
    for frame in ("TIT2", "TPE1", "APIC"):
        tags.delall(frame)
    tags.add(TIT2(encoding=3, text=title))
    if author:
        tags.add(TPE1(encoding=3, text=author))
    tags.add(APIC(encoding=3, mime="image/jpeg", type=PICTURE_TYPE_FRONT_COVER, desc="Cover", data=cover))


def _write_mp3(path: Path, title: str, author: str, cover: bytes) -> None:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    _apply_id3(tags, title, author, cover)
    tags.save(path, v2_version=3)  # O Windows lê ID3v2.3 melhor que a versão 2.4.


def _write_wav(path: Path, title: str, author: str, cover: bytes) -> None:
    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    _apply_id3(audio.tags, title, author, cover)
    audio.save(v2_version=3)


def _write_m4a(path: Path, title: str, author: str, cover: bytes) -> None:
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    audio.tags["\xa9nam"] = [title]
    audio.tags.pop("\xa9ART", None)
    if author:
        audio.tags["\xa9ART"] = [author]
    audio.tags["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def _write_flac(path: Path, title: str, author: str, cover: bytes) -> None:
    audio = FLAC(path)
    audio["title"] = title
    audio.pop("artist", None)
    if author:
        audio["artist"] = author
    picture = Picture()
    picture.type = PICTURE_TYPE_FRONT_COVER
    picture.mime = "image/jpeg"
    picture.desc = "Cover"
    picture.data = cover
    with Image.open(io.BytesIO(cover)) as image:
        picture.width, picture.height = image.size
    picture.depth = 24
    audio.clear_pictures()
    audio.add_picture(picture)
    audio.save()


_WRITERS = {".mp3": _write_mp3, ".wav": _write_wav, ".m4a": _write_m4a, ".flac": _write_flac}


class MutagenTagWriter:
    """Implementa TagWriter."""

    def write(self, path: Path, title: str, author: str, cover: bytes) -> None:
        writer = _WRITERS.get(path.suffix.lower())
        if writer is None:
            raise ExtractionError(f"O formato {path.suffix} não aceita nome, autor e capa.")
        try:
            writer(path, title, author, cover)
        except (MutagenError, OSError) as exc:
            raise ExtractionError(f"Não foi possível gravar os metadados: {exc}") from exc
