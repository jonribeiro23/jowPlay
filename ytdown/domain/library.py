"""A biblioteca: faixas extraídas pelo ytDown e as regras para agrupá-las, filtrá-las e ordená-las.

Estas funções são a definição de referência do comportamento da biblioteca. O
repositório SQLite pode usar SQL por desempenho, mas deve dar os mesmos resultados.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from ytdown.domain.text import search_key

class DuplicatePolicy(Enum):
    """O que fazer ao extrair um vídeo que já está na biblioteca (mesma URL de origem)."""

    REPLACE = auto()  # A faixa existente passa a usar o arquivo novo; o antigo vai para a Lixeira.
    KEEP_BOTH = auto()  # Uma faixa nova, ao lado da existente.


UNKNOWN_ARTIST = "Artista desconhecido"
UNKNOWN_ALBUM = "Álbum desconhecido"
UNKNOWN_GENRE = "Gênero desconhecido"


@dataclass(frozen=True)
class Track:
    """Uma faixa da biblioteca. `id` é None até a faixa ser salva no repositório."""

    rel_path: str  # Relativo à pasta da biblioteca, com "/" como separador.
    title: str
    added_at: datetime
    artist: str = ""
    album: str = ""
    genre: str = ""
    year: int | None = None
    track_no: int | None = None
    duration_ms: int = 0
    source_url: str | None = None  # URL do vídeo de origem: identifica duplicatas.
    play_count: int = 0
    last_played_at: datetime | None = None
    missing: bool = False  # O arquivo não foi encontrado na pasta da biblioteca.
    id: int | None = None

    @property
    def display_artist(self) -> str:
        return self.artist.strip() or UNKNOWN_ARTIST

    @property
    def display_album(self) -> str:
        return self.album.strip() or UNKNOWN_ALBUM

    @property
    def display_genre(self) -> str:
        return self.genre.strip() or UNKNOWN_GENRE


# --- resumos para navegação


@dataclass(frozen=True)
class ArtistSummary:
    name: str
    album_count: int
    track_count: int
    total_duration_ms: int
    cover_track_id: int | None  # Faixa cuja capa representa o artista.


@dataclass(frozen=True)
class AlbumSummary:
    title: str
    artist: str
    year: int | None
    track_count: int
    total_duration_ms: int
    cover_track_id: int | None  # Primeira faixa do álbum.


@dataclass(frozen=True)
class GenreSummary:
    name: str
    track_count: int
    total_duration_ms: int


def album_order(tracks: Iterable[Track]) -> list[Track]:
    """Faixas de um álbum na ordem de tocar: pelo nº da faixa (sem número por último), depois pelo título."""
    return sorted(tracks, key=lambda t: (t.track_no is None, t.track_no or 0, search_key(t.title)))


def _name_order(name: str, unknown: str) -> tuple[bool, str]:
    """Ordem alfabética sem diferenciar acentos, com o grupo "desconhecido" sempre no fim."""
    return (name == unknown, search_key(name))


def _group(tracks: Iterable[Track], key: Callable[[Track], object]) -> dict[object, list[Track]]:
    groups: dict[object, list[Track]] = {}
    for track in tracks:
        groups.setdefault(key(track), []).append(track)
    return groups


def summarize_albums(tracks: Iterable[Track]) -> list[AlbumSummary]:
    """Um álbum é identificado pelo nome e pelo artista: dois artistas com álbuns
    de mesmo nome não se misturam.
    """
    summaries = []
    for (title, artist), group in _group(tracks, lambda t: (t.display_album, t.display_artist)).items():
        ordered = album_order(group)
        years = [t.year for t in group if t.year is not None]
        summaries.append(
            AlbumSummary(
                title=title,
                artist=artist,
                year=min(years) if years else None,
                track_count=len(group),
                total_duration_ms=sum(t.duration_ms for t in group),
                cover_track_id=ordered[0].id,
            )
        )
    return sorted(
        summaries,
        key=lambda a: (_name_order(a.title, UNKNOWN_ALBUM), _name_order(a.artist, UNKNOWN_ARTIST)),
    )


def summarize_artists(tracks: Iterable[Track]) -> list[ArtistSummary]:
    summaries = []
    for name, group in _group(tracks, lambda t: t.display_artist).items():
        albums = summarize_albums(group)
        summaries.append(
            ArtistSummary(
                name=name,
                album_count=len(albums),
                track_count=len(group),
                total_duration_ms=sum(t.duration_ms for t in group),
                cover_track_id=albums[0].cover_track_id,
            )
        )
    return sorted(summaries, key=lambda a: _name_order(a.name, UNKNOWN_ARTIST))


def summarize_genres(tracks: Iterable[Track]) -> list[GenreSummary]:
    summaries = [
        GenreSummary(name=name, track_count=len(group), total_duration_ms=sum(t.duration_ms for t in group))
        for name, group in _group(tracks, lambda t: t.display_genre).items()
    ]
    return sorted(summaries, key=lambda g: _name_order(g.name, UNKNOWN_GENRE))


# --- filtro e ordenação


class SortField(Enum):
    TITLE = auto()
    ARTIST = auto()
    ALBUM = auto()
    GENRE = auto()
    YEAR = auto()
    TRACK_NO = auto()
    DURATION = auto()
    ADDED_AT = auto()
    PLAY_COUNT = auto()
    LAST_PLAYED = auto()


@dataclass(frozen=True)
class TrackQuery:
    """O que listar. `artist`, `album` e `genre` usam os nomes de exibição, então
    "Artista desconhecido" encontra as faixas sem artista.
    """

    text: str = ""  # Cada palavra precisa aparecer no título, artista, álbum ou gênero.
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    include_missing: bool = True
    sort: SortField = SortField.ARTIST
    descending: bool = False
    words: tuple[str, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "words", tuple(search_key(self.text).split()))


def matches(track: Track, query: TrackQuery) -> bool:
    if not query.include_missing and track.missing:
        return False
    if query.artist is not None and track.display_artist != query.artist:
        return False
    if query.album is not None and track.display_album != query.album:
        return False
    if query.genre is not None and track.display_genre != query.genre:
        return False
    searchable = search_key(" ".join((track.title, track.artist, track.album, track.genre)))
    return all(word in searchable for word in query.words)


_SORT_VALUES: dict[SortField, Callable[[Track], object]] = {
    SortField.TITLE: lambda t: search_key(t.title),
    SortField.ARTIST: lambda t: _name_order(t.display_artist, UNKNOWN_ARTIST),
    SortField.ALBUM: lambda t: _name_order(t.display_album, UNKNOWN_ALBUM),
    SortField.GENRE: lambda t: _name_order(t.display_genre, UNKNOWN_GENRE),
    SortField.YEAR: lambda t: t.year,
    SortField.TRACK_NO: lambda t: t.track_no,
    SortField.DURATION: lambda t: t.duration_ms,
    SortField.ADDED_AT: lambda t: t.added_at,
    SortField.PLAY_COUNT: lambda t: t.play_count,
    SortField.LAST_PLAYED: lambda t: t.last_played_at,
}


def _natural_order(track: Track) -> tuple:
    """Desempate: como as faixas aparecem em um álbum, agrupadas por artista e álbum."""
    return (
        _name_order(track.display_artist, UNKNOWN_ARTIST),
        _name_order(track.display_album, UNKNOWN_ALBUM),
        track.track_no is None,
        track.track_no or 0,
        search_key(track.title),
    )


def sort_tracks(tracks: Iterable[Track], sort: SortField, descending: bool = False) -> list[Track]:
    """Ordena pelo campo escolhido. Valores vazios (sem ano, nunca tocada...) ficam
    sempre no fim, em qualquer direção; empates seguem a ordem natural do álbum.
    """
    value = _SORT_VALUES[sort]
    ordered = sorted(tracks, key=_natural_order)
    present = [t for t in ordered if value(t) is not None]
    absent = [t for t in ordered if value(t) is None]
    return sorted(present, key=value, reverse=descending) + absent


def query_tracks(tracks: Iterable[Track], query: TrackQuery) -> list[Track]:
    return sort_tracks((t for t in tracks if matches(t, query)), query.sort, query.descending)
