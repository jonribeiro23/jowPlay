"""Metadados do arquivo de áudio: nome, autor e imagem de capa."""

from __future__ import annotations

import io
import sys
from pathlib import Path

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TIT2, TPE1, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE
from PIL import Image, ImageOps

RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
DEFAULT_COVER = RESOURCES / "default_cover.jpg"
MAX_COVER_SIZE = 1000  # Alguns players não exibem capas muito grandes.
PICTURE_TYPE_FRONT_COVER = 3


class InvalidCover(Exception):
    """A imagem não pôde ser lida. A mensagem é mostrada ao usuário."""


def load_cover(path: Path | None) -> bytes:
    """Devolve a capa em JPEG, o formato mais aceito pelos players.

    Sem `path`, usa a capa padrão. A proporção da imagem é preservada, e
    áreas transparentes ficam brancas, porque JPEG não tem transparência.
    """
    source = path or DEFAULT_COVER
    try:
        with Image.open(source) as image:
            rgba = ImageOps.exif_transpose(image).convert("RGBA")
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise InvalidCover(f"Não foi possível ler a imagem de capa: {source}") from exc

    cover = Image.new("RGB", rgba.size, "white")
    cover.paste(rgba, mask=rgba.getchannel("A"))
    cover.thumbnail((MAX_COVER_SIZE, MAX_COVER_SIZE))
    output = io.BytesIO()
    cover.save(output, format="JPEG", quality=90)
    return output.getvalue()


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


def write_tags(path: Path, title: str, author: str, cover: bytes) -> None:
    """Grava os metadados no arquivo. Autor vazio remove qualquer autor existente."""
    _WRITERS[path.suffix.lower()](path, title, author, cover)
