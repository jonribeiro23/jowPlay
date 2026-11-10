"""Gravação das etiquetas (nome, artista, álbum, gênero, ano, faixa, origem e capa) com mutagen.

Etiquetas usadas em cada formato:

| Campo        | MP3 e WAV (ID3v2.3) | M4A (MP4)               | FLAC (Vorbis)   |
| ------------ | ------------------- | ----------------------- | --------------- |
| Nome         | TIT2                | ©nam                    | TITLE           |
| Artista      | TPE1                | ©ART                    | ARTIST          |
| Álbum        | TALB                | ©alb                    | ALBUM           |
| Gênero       | TCON                | ©gen                    | GENRE           |
| Ano          | TYER                | ©day                    | DATE            |
| Nº da faixa  | TRCK                | trkn                    | TRACKNUMBER     |
| Origem       | WOAS                | ----:com.ytdown:source  | YTDOWN_SOURCE   |
| Capa         | APIC (frente)       | covr                    | PICTURE (frente)|
"""

from __future__ import annotations

import io
from pathlib import Path

from mutagen import MutagenError
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1, TRCK, WOAS, ID3NoHeaderError
from mutagen.mp4 import MP4, AtomDataType, MP4Cover, MP4FreeForm
from mutagen.wave import WAVE
from PIL import Image

from ytdown.domain.errors import ExtractionError
from ytdown.domain.models import AudioTags

PICTURE_TYPE_FRONT_COVER = 3
MP4_SOURCE_KEY = "----:com.ytdown:source"
VORBIS_SOURCE_KEY = "ytdown_source"

# Frames que o ytDown controla. O ano é criado como TDRC e convertido para TYER (v2.3) por update_to_v23.
_ID3_FRAMES = ("TIT2", "TPE1", "TALB", "TCON", "TDRC", "TYER", "TRCK", "WOAS", "APIC")


def _apply_id3(id3: ID3, tags: AudioTags) -> None:
    for frame in _ID3_FRAMES:
        id3.delall(frame)
    id3.add(TIT2(encoding=3, text=tags.title))
    for frame, value in ((TPE1, tags.artist), (TALB, tags.album), (TCON, tags.genre)):
        if value:
            id3.add(frame(encoding=3, text=value))
    if tags.year:
        id3.add(TDRC(encoding=3, text=str(tags.year)))
    if tags.track_no:
        id3.add(TRCK(encoding=3, text=str(tags.track_no)))
    if tags.source_url:
        id3.add(WOAS(url=tags.source_url))
    id3.add(APIC(encoding=3, mime="image/jpeg", type=PICTURE_TYPE_FRONT_COVER, desc="Cover", data=tags.cover))
    # Salvar com v2_version=3 não converte os frames sozinho: sem isto, o ano iria como
    # TDRC (exclusivo da v2.4) dentro de um arquivo v2.3, e o Windows não o mostraria.
    id3.update_to_v23()


def _write_mp3(path: Path, tags: AudioTags) -> None:
    try:
        id3 = ID3(path)
    except ID3NoHeaderError:
        id3 = ID3()
    _apply_id3(id3, tags)
    id3.save(path, v2_version=3)  # O Windows lê ID3v2.3 melhor que a versão 2.4.


def _write_wav(path: Path, tags: AudioTags) -> None:
    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    _apply_id3(audio.tags, tags)
    audio.save(v2_version=3)


def _set_or_remove(container, key: str, value) -> None:
    if value:
        container[key] = value
    else:
        container.pop(key, None)


def _write_m4a(path: Path, tags: AudioTags) -> None:
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    mp4 = audio.tags
    mp4["\xa9nam"] = [tags.title]
    _set_or_remove(mp4, "\xa9ART", [tags.artist] if tags.artist else None)
    _set_or_remove(mp4, "\xa9alb", [tags.album] if tags.album else None)
    _set_or_remove(mp4, "\xa9gen", [tags.genre] if tags.genre else None)
    _set_or_remove(mp4, "\xa9day", [str(tags.year)] if tags.year else None)
    _set_or_remove(mp4, "trkn", [(tags.track_no, 0)] if tags.track_no else None)
    source = [MP4FreeForm(tags.source_url.encode(), dataformat=AtomDataType.UTF8)] if tags.source_url else None
    _set_or_remove(mp4, MP4_SOURCE_KEY, source)
    mp4["covr"] = [MP4Cover(tags.cover, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def _write_flac(path: Path, tags: AudioTags) -> None:
    audio = FLAC(path)
    audio["title"] = tags.title
    _set_or_remove(audio, "artist", tags.artist)
    _set_or_remove(audio, "album", tags.album)
    _set_or_remove(audio, "genre", tags.genre)
    _set_or_remove(audio, "date", str(tags.year) if tags.year else None)
    _set_or_remove(audio, "tracknumber", str(tags.track_no) if tags.track_no else None)
    _set_or_remove(audio, VORBIS_SOURCE_KEY, tags.source_url)
    audio.clear_pictures()
    audio.add_picture(_flac_picture(tags.cover))
    audio.save()


def _flac_picture(cover: bytes) -> Picture:
    picture = Picture()
    picture.type = PICTURE_TYPE_FRONT_COVER
    picture.mime = "image/jpeg"
    picture.desc = "Cover"
    picture.data = cover
    with Image.open(io.BytesIO(cover)) as image:
        picture.width, picture.height = image.size
    picture.depth = 24
    return picture


_WRITERS = {".mp3": _write_mp3, ".wav": _write_wav, ".m4a": _write_m4a, ".flac": _write_flac}


class MutagenTagWriter:
    """Implementa TagWriter."""

    def write(self, path: Path, tags: AudioTags) -> None:
        writer = _WRITERS.get(path.suffix.lower())
        if writer is None:
            raise ExtractionError(f"O formato {path.suffix} não aceita nome, autor e capa.")
        try:
            writer(path, tags)
        except (MutagenError, OSError) as exc:
            raise ExtractionError(f"Não foi possível gravar os metadados: {exc}") from exc

    def update(self, path: Path, changes: dict) -> None:
        """Altera somente os campos informados; capa None remove a capa frontal.

        O chamador deve trabalhar em uma cópia: esta operação não é transacional.
        """
        fields = {"title", "artist", "album", "genre", "year", "track_no", "cover"}
        if changes.keys() - fields:
            raise ValueError("Campo de etiqueta não suportado")
        if not changes:
            return
        try:
            suffix = path.suffix.lower()
            if suffix in (".mp3", ".wav"):
                audio = WAVE(path) if suffix == ".wav" else None
                if audio is not None:
                    if audio.tags is None:
                        audio.add_tags()
                    tags = audio.tags
                else:
                    try:
                        tags = ID3(path)
                    except ID3NoHeaderError:
                        tags = ID3()
                frames = {"title": TIT2, "artist": TPE1, "album": TALB,
                          "genre": TCON, "year": TDRC, "track_no": TRCK}
                for name, cls in frames.items():
                    if name in changes:
                        tags.delall(cls.__name__)
                        if name == "year":
                            tags.delall("TYER")
                        if changes[name] is not None and changes[name] != "":
                            tags.add(cls(encoding=3, text=str(changes[name])))
                if "cover" in changes:
                    for picture in list(tags.getall("APIC")):
                        if picture.type == PICTURE_TYPE_FRONT_COVER:
                            del tags[picture.HashKey]
                    if changes["cover"]:
                        descriptions = {picture.desc for picture in tags.getall("APIC")}
                        description = "Cover"
                        while description in descriptions:
                            description += "_"
                        tags.add(APIC(encoding=3, mime="image/jpeg", type=PICTURE_TYPE_FRONT_COVER,
                                      desc=description, data=changes["cover"]))
                version = 3 if tags.version[1] == 3 else 4
                if version == 3:
                    tags.update_to_v23()
                if audio is not None:
                    audio.save(v2_version=version)
                else:
                    tags.save(path, v2_version=version)
            elif suffix == ".m4a":
                audio = MP4(path)
                if audio.tags is None:
                    audio.add_tags()
                keys = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb",
                        "genre": "\xa9gen", "year": "\xa9day", "track_no": "trkn", "cover": "covr"}
                for name, value in changes.items():
                    if value is None or value == "" or (name == "cover" and not value):
                        audio.tags.pop(keys[name], None)
                    elif name == "cover":
                        audio.tags[keys[name]] = [MP4Cover(value, imageformat=MP4Cover.FORMAT_JPEG)]
                    elif name == "track_no":
                        audio.tags[keys[name]] = [(value, 0)]
                    else:
                        audio.tags[keys[name]] = [str(value)]
                audio.save()
            elif suffix == ".flac":
                audio = FLAC(path)
                keys = {"title": "title", "artist": "artist", "album": "album", "genre": "genre",
                        "year": "date", "track_no": "tracknumber"}
                for name, value in changes.items():
                    if name == "cover":
                        other = [p for p in audio.pictures if p.type != PICTURE_TYPE_FRONT_COVER]
                        audio.clear_pictures()
                        for picture in other:
                            audio.add_picture(picture)
                        if value:
                            audio.add_picture(_flac_picture(value))
                    else:
                        _set_or_remove(audio, keys[name], str(value) if value is not None else None)
                audio.save()
            else:
                raise ExtractionError(f"O formato {path.suffix} não aceita edição de etiquetas.")
        except (MutagenError, OSError) as exc:
            raise ExtractionError(f"Não foi possível gravar os metadados: {exc}") from exc
