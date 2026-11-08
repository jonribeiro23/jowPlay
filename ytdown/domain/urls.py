"""Regras sobre as URLs aceitas."""

from __future__ import annotations

from urllib.parse import urlparse

YOUTUBE_HOSTS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
})


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
