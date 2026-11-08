"""Dublês das interfaces de application.ports, para testar os casos de uso sem rede."""

from __future__ import annotations

import threading
from pathlib import Path

from ytdown.application.ports import DownloadedAudio
from ytdown.domain.errors import InvalidCover
from ytdown.domain.models import AudioFormat, Progress, Stage

DEFAULT_COVER = b"capa-padrao"


class FakeDownloader:
    """"Baixa" criando um arquivo de áudio falso em `work_dir`."""

    def __init__(self, title: str | None = "video", error: Exception | None = None, on_download=None) -> None:
        self.title = title
        self.error = error
        self.on_download = on_download
        self.calls: list[str] = []

    def download(self, url, work_dir: Path, audio_format: AudioFormat, on_progress, cancel: threading.Event):
        self.calls.append(url)
        on_progress(Progress(Stage.DOWNLOADING, 50))
        if self.on_download:
            self.on_download()
        if self.error:
            raise self.error
        path = work_dir / f"{self.title or 'sem-titulo'}.{audio_format.extension}"
        path.write_bytes(b"audio")
        return DownloadedAudio(path, self.title)


class FakeCovers:
    def __init__(self, valid: set[Path] | None = None) -> None:
        self.valid = valid or set()

    def load(self, path: Path | None) -> bytes:
        if path is None:
            return DEFAULT_COVER
        if path not in self.valid:
            raise InvalidCover(f"Não foi possível ler a imagem de capa: {path}")
        return f"capa:{path.name}".encode()


class FakeTags:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, bytes]] = []

    def write(self, path: Path, title: str, author: str, cover: bytes) -> None:
        self.calls.append((path.name, title, author, cover))


class FakeDevices:
    server_id = "pc-de-teste"

    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}

    def add_device(self, name: str) -> str:
        token = f"token-{len(self.tokens)}"
        self.tokens[token] = name
        return token

    def knows(self, token: str) -> bool:
        return token in self.tokens
