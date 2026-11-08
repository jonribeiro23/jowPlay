"""Dublês das interfaces de application.ports, para testar os casos de uso sem rede."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

from ytdown.application.ports import DownloadedAudio
from ytdown.domain import library
from ytdown.domain.errors import InvalidCover
from ytdown.domain.library import Track, TrackQuery
from ytdown.domain.models import AudioFormat, AudioTags, Progress, Stage

DEFAULT_COVER = b"capa-padrao"
SOURCE_URL = "https://www.youtube.com/watch?v=video"


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
        return DownloadedAudio(path, self.title, SOURCE_URL)


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
        self.calls: list[tuple[str, AudioTags]] = []

    def write(self, path: Path, tags: AudioTags) -> None:
        self.calls.append((path.name, tags))


class InMemoryTrackRepository:
    """TrackRepository em memória, usando as funções de referência do domínio."""

    def __init__(self) -> None:
        self._tracks: dict[int, Track] = {}
        self._next_id = 1

    def add(self, track: Track) -> Track:
        saved = replace(track, id=self._next_id)
        self._tracks[saved.id] = saved
        self._next_id += 1
        return saved

    def update(self, track: Track) -> None:
        if track.id not in self._tracks:
            raise KeyError(track.id)
        self._tracks[track.id] = track

    def remove(self, track_id: int) -> None:
        self._tracks.pop(track_id, None)

    def get(self, track_id: int) -> Track | None:
        return self._tracks.get(track_id)

    def find_by_source_url(self, url: str) -> Track | None:
        return next((t for t in self._tracks.values() if t.source_url == url), None)

    def find_by_path(self, rel_path: str) -> Track | None:
        return next((t for t in self._tracks.values() if t.rel_path == rel_path), None)

    def list_tracks(self, query: TrackQuery = TrackQuery()) -> list[Track]:
        return library.query_tracks(self._tracks.values(), query)

    def artists(self) -> list[library.ArtistSummary]:
        return library.summarize_artists(self._tracks.values())

    def albums(self, artist: str | None = None) -> list[library.AlbumSummary]:
        tracks = [t for t in self._tracks.values() if artist is None or t.display_artist == artist]
        return library.summarize_albums(tracks)

    def genres(self) -> list[library.GenreSummary]:
        return library.summarize_genres(self._tracks.values())


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
