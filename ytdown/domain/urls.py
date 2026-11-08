"""Regras sobre as URLs aceitas."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

YOUTUBE_HOSTS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
})
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ID_IN_PATH = ("shorts", "live", "embed", "v")  # youtube.com/shorts/<id>, /live/<id>...


def video_id(url: str) -> str | None:
    """O identificador do vídeo (11 caracteres) em qualquer forma de link do YouTube, ou None."""
    if not is_youtube_url(url):
        return None
    parsed = urlparse(url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname == "youtu.be":
        candidate = parts[0] if parts else ""
    elif parts[:1] == ["watch"]:
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    elif len(parts) >= 2 and parts[0] in _ID_IN_PATH:
        candidate = parts[1]
    else:
        return None
    return candidate if _VIDEO_ID.match(candidate) else None


def canonical_video_url(url: str) -> str | None:
    """O endereço que o yt-dlp informa como `webpage_url` (e que vai para as etiquetas como
    URL de origem). Assim, uma duplicata é reconhecida antes de baixar.
    """
    found = video_id(url)
    return f"https://www.youtube.com/watch?v={found}" if found else None


def is_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and parsed.hostname in YOUTUBE_HOSTS
    except ValueError:
        return False


def parse_url_list(text: str) -> tuple[list[str], list[int]]:
    """Lê uma URL por linha. Devolve (URLs sem repetição, números das linhas inválidas).

    Linhas em branco são ignoradas; a numeração das linhas começa em 1.
    """
    urls: list[str] = []
    invalid: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        url = line.strip()
        if not url:
            continue
        if not is_youtube_url(url):
            invalid.append(number)
        elif url not in urls:
            urls.append(url)
    return urls, invalid
