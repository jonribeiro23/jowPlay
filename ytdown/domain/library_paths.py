"""Onde cada faixa fica dentro da pasta da biblioteca: `Artista/Álbum/NN - Título.ext`.

O caminho é relativo à pasta da biblioteca e usa "/" como separador. As regras evitam
o que o Windows não aceita em nomes de arquivo e mantêm o caminho completo curto.
"""

from __future__ import annotations

import re

from ytdown.domain.library import UNKNOWN_ALBUM, UNKNOWN_ARTIST

UNTITLED = "Sem título"
MAX_FOLDER_NAME = 50  # Artista e álbum.
MIN_FOLDER_NAME = 10  # Até onde artista e álbum encolhem quando falta espaço.
MAX_RELATIVE_PATH = 200  # Sobra espaço para a pasta da biblioteca dentro dos 260 caracteres do Windows.
MIN_FILE_STEM = 20  # Nunca encurta o nome do arquivo abaixo disso para caber em `max_length`.

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_name(text: str, fallback: str, max_length: int) -> str:
    """Um nome de arquivo ou pasta aceito pelo Windows."""
    name = " ".join(_FORBIDDEN.sub("_", text).split())
    name = name[:max_length].rstrip(" .")  # O Windows não aceita nomes terminados em ponto ou espaço.
    if not name.strip("_"):
        name = fallback
    if name.split(".")[0].upper() in _RESERVED:
        name += "_"  # "CON", "nul.txt"... são nomes de dispositivos no Windows.
    return name


def library_path(
    artist: str,
    album: str,
    title: str,
    track_no: int | None,
    extension: str,
    max_length: int = MAX_RELATIVE_PATH,
) -> str:
    """Caminho relativo da faixa na biblioteca. Para caber em `max_length` caracteres,
    encurta primeiro o nome do arquivo e, se ainda faltar espaço, os nomes do artista
    e do álbum (até os mínimos MIN_FILE_STEM e MIN_FOLDER_NAME).
    """
    suffix = "." + extension.lower().lstrip(".")
    prefix = f"{track_no:02d} - " if track_no else ""
    available = max_length - len(suffix) - len(prefix) - 2  # 2 = as duas barras.
    folder_limit = min(MAX_FOLDER_NAME, max(MIN_FOLDER_NAME, (available - MIN_FILE_STEM) // 2))
    artist_name = safe_name(artist, UNKNOWN_ARTIST, folder_limit)
    album_name = safe_name(album, UNKNOWN_ALBUM, folder_limit)
    room_for_title = max(available - len(artist_name) - len(album_name), MIN_FILE_STEM)
    return f"{artist_name}/{album_name}/{prefix}{safe_name(title, UNTITLED, room_for_title)}{suffix}"
