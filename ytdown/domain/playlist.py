"""Regras de playlists; cada posição representa uma ocorrência independente."""

from dataclasses import dataclass
from unicodedata import normalize

from ytdown.domain.library import Track


def playlist_name(name: str) -> str:
    name = normalize("NFC", name.strip())
    if not name:
        raise ValueError("O nome da playlist não pode ficar vazio")
    return name


def playlist_name_key(name: str) -> str:
    return normalize("NFC", playlist_name(name).casefold())


@dataclass(frozen=True)
class Playlist:
    name: str
    tracks: tuple[Track, ...] = ()
    id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", playlist_name(self.name))
        object.__setattr__(self, "tracks", tuple(self.tracks))

    @property
    def duration_ms(self) -> int:
        return sum(track.duration_ms for track in self.tracks)
