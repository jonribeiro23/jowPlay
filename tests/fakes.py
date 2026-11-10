"""Dublês das interfaces de application.ports, para testar os casos de uso sem rede."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

from ytdown.application.ports import DownloadedAudio, PlayerState
from ytdown.domain import library
from ytdown.domain.errors import InvalidCover, LibraryError, UnreadableAudio
from ytdown.domain.library import DuplicatePolicy, Track, TrackQuery
from ytdown.domain.models import AudioFileInfo, AudioFormat, AudioTags, Progress, Stage

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


class FakeReader:
    """MetadataReader que só informa a duração (ou falha, se `unreadable`)."""

    def __init__(self, duration_ms: int = 180_000, unreadable: bool = False) -> None:
        self.duration_ms = duration_ms
        self.unreadable = unreadable

    def read(self, path: Path) -> AudioFileInfo:
        if self.unreadable:
            raise UnreadableAudio(f"Formato não suportado: {path.name}")
        return AudioFileInfo(duration_ms=self.duration_ms)

    def read_cover(self, path: Path) -> bytes | None:
        return None


class FakeLibraryStorage:
    """LibraryStorage em memória: guarda o conteúdo de cada arquivo pelo caminho relativo.
    Como o real, nunca sobrescreve: um nome ocupado ganha " (1)", " (2)"...
    """

    def __init__(self, root: Path = Path("C:/Musica/ytDown"), max_length: int = 200) -> None:
        self._root = root
        self.max_length = max_length
        self.files: dict[str, bytes] = {}
        self.available = True
        self.trashed: list[str] = []
        self.discarded: list[str] = []
        self.fail_trash = False

    @property
    def root(self) -> Path:
        return self._root

    def is_available(self) -> bool:
        return self.available

    def absolute(self, rel_path: str) -> Path:
        return self._root.joinpath(*rel_path.split("/"))

    def exists(self, rel_path: str) -> bool:
        return rel_path in self.files

    def max_relative_length(self) -> int:
        return self.max_length

    def place(self, source: Path, rel_path: str) -> str:
        final = self._free_name(rel_path)
        self.files[final] = source.read_bytes()
        source.unlink()
        return final

    def move(self, rel_path: str, new_rel_path: str) -> str:
        content = self.files.pop(rel_path)
        final = self._free_name(new_rel_path)
        self.files[final] = content
        return final

    def trash(self, rel_path: str) -> None:
        if self.fail_trash:
            raise LibraryError(f"Não foi possível enviar {rel_path} para a Lixeira: em uso")
        del self.files[rel_path]
        self.trashed.append(rel_path)

    def discard(self, rel_path: str) -> None:
        self.files.pop(rel_path, None)
        self.discarded.append(rel_path)

    def relocate(self, new_root, on_progress):
        raise NotImplementedError

    def _free_name(self, rel_path: str) -> str:
        stem, dot, suffix = rel_path.rpartition(".")
        candidate, counter = rel_path, 1
        while candidate in self.files:
            candidate = f"{stem} ({counter}){dot}{suffix}"
            counter += 1
        return candidate


class FakeDestination:
    def __init__(self, folder: Path, policy: DuplicatePolicy) -> None:
        self.folder, self.policy = folder, policy


class FakeLibrary:
    """Imita o RegisterExtractedTrack no que a página usa: pasta, duplicatas e destino."""

    def __init__(self, folder=Path("C:/Musica"), duplicates=None):
        self.folder = folder
        self.duplicates = duplicates or {}  # url -> Track

    def find_duplicates(self, urls):
        return [(url, self.duplicates[url]) for url in urls if url in self.duplicates]

    def destination(self, on_duplicate=DuplicatePolicy.KEEP_BOTH):
        return FakeDestination(self.folder, on_duplicate)


class FakeAudioPlayer:
    """AudioPlayer sem som, para os testes do caso de uso de reprodução.

    Faz o que o real faz de forma síncrona e deixa o teste provocar o resto: `advance` (a faixa
    andou), `finish` (terminou sozinha) e `fail` (erro ao tocar). `durations` dá a duração de
    cada arquivo; um arquivo em `broken` falha ao carregar.
    """

    def __init__(self, durations: dict[Path, int] | None = None) -> None:
        self.durations = durations or {}
        self.broken: set[Path] = set()
        self.listener = None
        self.loaded: list[Path] = []
        self.path: Path | None = None
        self._state = PlayerState.STOPPED
        self._position = 0
        self.volume = 80
        self.muted = False

    def set_listener(self, listener) -> None:
        self.listener = listener

    def load(self, path: Path) -> None:
        self._set_state(PlayerState.STOPPED)
        self.loaded.append(path)
        self._position = 0
        if path in self.broken:
            self.path = None
            self.listener.on_error(f"Não foi possível tocar \"{path.name}\".")
            return
        self.path = path
        self.listener.on_duration(self.duration_ms)

    def play(self) -> None:
        if self.path is not None:
            self._set_state(PlayerState.PLAYING)

    def pause(self) -> None:
        if self._state is PlayerState.PLAYING:
            self._set_state(PlayerState.PAUSED)

    def stop(self) -> None:
        self._position = 0
        self._set_state(PlayerState.STOPPED)

    def seek(self, position_ms: int) -> None:
        self._position = max(0, position_ms)
        self.listener.on_position(self._position)

    @property
    def state(self) -> PlayerState:
        return self._state

    @property
    def position_ms(self) -> int:
        return self._position

    @property
    def duration_ms(self) -> int:
        return self.durations.get(self.path, 180_000) if self.path else 0

    def set_volume(self, volume: int) -> None:
        self.volume = min(100, max(0, volume))

    def set_muted(self, muted: bool) -> None:
        self.muted = muted

    # --- o teste provoca

    def advance(self, ms: int) -> None:
        self._position += ms
        self.listener.on_position(self._position)

    def finish(self) -> None:
        self._position = self.duration_ms
        self._set_state(PlayerState.STOPPED)
        self.listener.on_finished()

    def fail(self, message: str = "Não foi possível tocar o áudio.") -> None:
        self._set_state(PlayerState.STOPPED)
        self.listener.on_error(message)

    def _set_state(self, state: PlayerState) -> None:
        if state is not self._state:
            self._state = state
            if self.listener:
                self.listener.on_state(state)


class InMemoryTrackRepository:
    """TrackRepository em memória, usando as funções de referência do domínio."""

    def __init__(self) -> None:
        self._tracks: dict[int, Track] = {}
        self._next_id = 1

    def add(self, track: Track) -> Track:
        if self.find_by_path(track.rel_path):
            raise ValueError(f"Já existe uma faixa em {track.rel_path}")
        saved = replace(track, id=self._next_id)
        self._tracks[saved.id] = saved
        self._next_id += 1
        return saved

    def update(self, track: Track) -> None:
        if track.id not in self._tracks:
            raise KeyError(track.id)
        self._tracks[track.id] = track

    def record_play(self, track_id, played_at):
        track = self.get(track_id)
        if track is None:
            return None
        track = replace(track, play_count=track.play_count + 1, last_played_at=played_at)
        self._tracks[track_id] = track
        return track

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
