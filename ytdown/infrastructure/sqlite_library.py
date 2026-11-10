"""Índice da biblioteca em SQLite.

Busca, ordenação e resumos acontecem no SQL, sobre colunas derivadas (textos
normalizados, nomes de exibição) calculadas pelas funções do domínio no momento da
gravação. O teste de contrato (tests/contracts/track_repository.py) garante que os
resultados são iguais aos das funções de referência em ytdown.domain.library.
"""

from __future__ import annotations

import functools
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from ytdown.domain.errors import LibraryError
from ytdown.domain.library import (
    UNKNOWN_ALBUM,
    UNKNOWN_ARTIST,
    UNKNOWN_GENRE,
    AlbumSummary,
    ArtistSummary,
    GenreSummary,
    SortField,
    Track,
    TrackQuery,
)
from ytdown.domain.text import search_key

# Cada migração leva o banco da versão anterior para a do seu número. Nunca altere
# uma migração já publicada: acrescente uma nova.
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY,
            rel_path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            artist TEXT NOT NULL DEFAULT '',
            album TEXT NOT NULL DEFAULT '',
            genre TEXT NOT NULL DEFAULT '',
            year INTEGER,
            track_no INTEGER,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            source_url TEXT,
            added_at TEXT NOT NULL,
            play_count INTEGER NOT NULL DEFAULT 0,
            last_played_at TEXT,
            missing INTEGER NOT NULL DEFAULT 0,
            -- Derivadas: calculadas pelas regras do domínio a cada gravação.
            title_key TEXT NOT NULL,
            artist_display TEXT NOT NULL,
            artist_key TEXT NOT NULL,
            artist_unknown INTEGER NOT NULL,
            album_display TEXT NOT NULL,
            album_key TEXT NOT NULL,
            album_unknown INTEGER NOT NULL,
            genre_display TEXT NOT NULL,
            genre_key TEXT NOT NULL,
            genre_unknown INTEGER NOT NULL,
            search_text TEXT NOT NULL
        );
        CREATE INDEX tracks_artist ON tracks (artist_display);
        CREATE INDEX tracks_album ON tracks (album_display, artist_display);
        CREATE INDEX tracks_genre ON tracks (genre_display);
        CREATE INDEX tracks_source_url ON tracks (source_url);
        """,
    ),
    (2, """
        CREATE TABLE playlists (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            name_key TEXT NOT NULL UNIQUE
        );
        CREATE TABLE playlist_tracks (
            playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            PRIMARY KEY (playlist_id, position)
        );
        CREATE INDEX playlist_tracks_track ON playlist_tracks(track_id);
    """),
]


_COLUMNS = (
    "id, rel_path, title, artist, album, genre, year, track_no, duration_ms, "
    "source_url, added_at, play_count, last_played_at, missing"
)

# Expressões de ordenação equivalentes a library._SORT_VALUES. Campos que podem
# faltar (anuláveis) ficam sempre no fim, em qualquer direção.
_SORT_COLUMNS: dict[SortField, tuple[str, ...]] = {
    SortField.TITLE: ("title_key",),
    SortField.ARTIST: ("artist_unknown", "artist_key"),
    SortField.ALBUM: ("album_unknown", "album_key"),
    SortField.GENRE: ("genre_unknown", "genre_key"),
    SortField.YEAR: ("year",),
    SortField.TRACK_NO: ("track_no",),
    SortField.DURATION: ("duration_ms",),
    SortField.ADDED_AT: ("added_at",),
    SortField.PLAY_COUNT: ("play_count",),
    SortField.LAST_PLAYED: ("last_played_at",),
}
_NULLABLE_SORTS = {SortField.YEAR, SortField.TRACK_NO, SortField.LAST_PLAYED}
# Desempate igual a library._natural_order; o id mantém a ordem de inclusão nos empates totais.
_NATURAL_ORDER = (
    "artist_unknown, artist_key, album_unknown, album_key, "
    "track_no IS NULL, COALESCE(track_no, 0), title_key, id"
)


# Um álbum por (nome, artista), com a capa da primeira faixa na ordem de library.album_order.
_ALBUMS_SQL = """
    SELECT album_display, artist_display, MIN(album_unknown) AS album_unknown, MIN(album_key) AS album_key,
           MIN(artist_unknown) AS artist_unknown, MIN(artist_key) AS artist_key, MIN(year) AS year,
           COUNT(*) AS track_count, SUM(duration_ms) AS total_duration_ms, MIN(id) AS first_id,
           MAX(CASE WHEN position = 1 THEN id END) AS cover_track_id
    FROM (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY album_display, artist_display
            ORDER BY track_no IS NULL, COALESCE(track_no, 0), title_key, id
        ) AS position
        FROM tracks {where}
    )
    GROUP BY album_display, artist_display
"""
_ALBUM_ORDER = "album_unknown, album_key, artist_unknown, artist_key, first_id"


def default_library_db_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ytDown" / "library.db"


def _to_db(moment: datetime | None) -> str | None:
    # Largura fixa (sempre com microssegundos): a ordem do texto é a ordem do tempo.
    return moment.isoformat(timespec="microseconds") if moment else None


def _from_db(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None  # Bem mais rápido que strptime.


def _derived(track: Track) -> dict:
    return {
        "title_key": search_key(track.title),
        "artist_display": track.display_artist,
        "artist_key": search_key(track.display_artist),
        "artist_unknown": track.display_artist == UNKNOWN_ARTIST,
        "album_display": track.display_album,
        "album_key": search_key(track.display_album),
        "album_unknown": track.display_album == UNKNOWN_ALBUM,
        "genre_display": track.display_genre,
        "genre_key": search_key(track.display_genre),
        "genre_unknown": track.display_genre == UNKNOWN_GENRE,
        "search_text": search_key(" ".join((track.title, track.artist, track.album, track.genre))),
    }


def _values(track: Track) -> dict:
    return {
        "rel_path": track.rel_path,
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "genre": track.genre,
        "year": track.year,
        "track_no": track.track_no,
        "duration_ms": track.duration_ms,
        "source_url": track.source_url,
        "added_at": _to_db(track.added_at),
        "play_count": track.play_count,
        "last_played_at": _to_db(track.last_played_at),
        "missing": track.missing,
        **_derived(track),
    }


def _track(row: sqlite3.Row) -> Track:
    return Track(
        id=row["id"],
        rel_path=row["rel_path"],
        title=row["title"],
        artist=row["artist"],
        album=row["album"],
        genre=row["genre"],
        year=row["year"],
        track_no=row["track_no"],
        duration_ms=row["duration_ms"],
        source_url=row["source_url"],
        added_at=_from_db(row["added_at"]),
        play_count=row["play_count"],
        last_played_at=_from_db(row["last_played_at"]),
        missing=bool(row["missing"]),
    )


def _locked(method):
    """Uma operação por vez na conexão, venha de que thread vier."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class SqliteTrackRepository:
    """Implementa TrackRepository.

    Pode ser usado por várias threads (a extração registra faixas fora da thread da
    interface): cada operação roda inteira, uma de cada vez, na mesma conexão.
    """

    def __init__(self, path: Path, migrations: list[tuple[int, str]] = MIGRATIONS) -> None:
        self._lock = threading.RLock()
        self._db: sqlite3.Connection | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(path, check_same_thread=False)
            self._db.row_factory = sqlite3.Row
            # WAL: uma importação pode gravar enquanto a interface lê.
            self._db.execute("PRAGMA journal_mode = WAL")
            self._db.execute("PRAGMA foreign_keys = ON")
            self._migrate(migrations)
        except (sqlite3.Error, LibraryError) as exc:
            if self._db is not None:
                self._db.close()  # Senão o arquivo continua preso até o fim do processo.
            if isinstance(exc, LibraryError):
                raise
            raise LibraryError(f"Não foi possível abrir a biblioteca em {path}: {exc}") from exc

    @_locked
    def close(self) -> None:
        self._db.close()

    @property
    @_locked
    def schema_version(self) -> int:
        return self._db.execute("SELECT version FROM schema_version").fetchone()[0]

    def _migrate(self, migrations: list[tuple[int, str]]) -> None:
        with self._db:
            self._db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            if self._db.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
                self._db.execute("INSERT INTO schema_version (version) VALUES (0)")
        current = self.schema_version
        latest = max((number for number, _ in migrations), default=0)
        if current > latest:
            raise LibraryError(
                "A biblioteca foi criada por uma versão mais nova do ytDown. Atualize o app para abri-la."
            )
        for number, script in sorted(migrations):
            if number > current:
                self._apply(number, script)

    def _apply(self, number: int, script: str) -> None:
        """Cada migração roda inteira ou não roda: um erro no meio não deixa o banco pela metade."""
        try:
            self._db.executescript(f"BEGIN; {script}; UPDATE schema_version SET version = {int(number)}; COMMIT;")
        except sqlite3.Error:
            if self._db.in_transaction:
                self._db.rollback()
            raise

    # --- gravação

    @_locked
    def add(self, track: Track) -> Track:
        values = _values(track)
        columns = ", ".join(values)
        placeholders = ", ".join(f":{name}" for name in values)
        try:
            with self._db:
                cursor = self._db.execute(f"INSERT INTO tracks ({columns}) VALUES ({placeholders})", values)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Já existe uma faixa em {track.rel_path}") from exc
        return self.get(cursor.lastrowid)

    @_locked
    def update(self, track: Track) -> None:
        values = _values(track)
        assignments = ", ".join(f"{name} = :{name}" for name in values)
        with self._db:
            cursor = self._db.execute(f"UPDATE tracks SET {assignments} WHERE id = :id", {**values, "id": track.id})
        if cursor.rowcount == 0:
            raise KeyError(track.id)

    @_locked
    def record_play(self, track_id: int, played_at: datetime) -> Track | None:
        with self._db:
            cursor = self._db.execute(
                "UPDATE tracks SET play_count = play_count + 1, last_played_at = ? WHERE id = ?",
                (_to_db(played_at), track_id),
            )
            return self.get(track_id) if cursor.rowcount else None

    @_locked
    def remove(self, track_id: int) -> None:
        with self._db:
            self._db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))

    @_locked
    def remove_with_file(self, track_id: int, remove_file) -> None:
        with self._db:
            cursor = self._db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
            if not cursor.rowcount:
                raise KeyError(track_id)
            remove_file()

    # --- consultas

    @_locked
    def get(self, track_id: int) -> Track | None:
        return self._one("SELECT {columns} FROM tracks WHERE id = ?", track_id)

    @_locked
    def find_by_source_url(self, url: str) -> Track | None:
        return self._one("SELECT {columns} FROM tracks WHERE source_url = ? ORDER BY id LIMIT 1", url)

    @_locked
    def find_by_path(self, rel_path: str) -> Track | None:
        return self._one("SELECT {columns} FROM tracks WHERE rel_path = ?", rel_path)

    @_locked
    def list_tracks(self, query: TrackQuery = TrackQuery()) -> list[Track]:
        conditions, params = [], []
        if not query.include_missing:
            conditions.append("missing = 0")
        for column, value in (("artist_display", query.artist), ("album_display", query.album),
                              ("genre_display", query.genre)):
            if value is not None:
                conditions.append(f"{column} = ?")
                params.append(value)
        for word in query.words:
            conditions.append("instr(search_text, ?) > 0")
            params.append(word)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT {_COLUMNS} FROM tracks {where} ORDER BY {self._order_by(query)}"
        return [_track(row) for row in self._db.execute(sql, params)]

    @staticmethod
    def _order_by(query: TrackQuery) -> str:
        direction = "DESC" if query.descending else "ASC"
        columns = _SORT_COLUMNS[query.sort]
        parts = [f"{columns[0]} IS NULL"] if query.sort in _NULLABLE_SORTS else []
        parts += [f"{column} {direction}" for column in columns]
        return ", ".join([*parts, _NATURAL_ORDER])

    # Resumos em SQL, equivalentes a library.summarize_*. Nos empates de nome
    # normalizado (ex.: "Rock" e "rock"), vale o grupo que apareceu primeiro (menor id).

    @_locked
    def albums(self, artist: str | None = None) -> list[AlbumSummary]:
        where, params = ("WHERE artist_display = ?", (artist,)) if artist is not None else ("", ())
        rows = self._db.execute(f"{_ALBUMS_SQL.format(where=where)} ORDER BY {_ALBUM_ORDER}", params)
        return [
            AlbumSummary(row["album_display"], row["artist_display"], row["year"], row["track_count"],
                         row["total_duration_ms"], row["cover_track_id"])
            for row in rows
        ]

    @_locked
    def artists(self) -> list[ArtistSummary]:
        sql = f"""
            WITH albums AS ({_ALBUMS_SQL.format(where="")}),
            first_album AS (
                SELECT artist_display, cover_track_id,
                       ROW_NUMBER() OVER (PARTITION BY artist_display ORDER BY {_ALBUM_ORDER}) AS position
                FROM albums
            )
            SELECT t.artist_display, COUNT(DISTINCT t.album_display) AS album_count, COUNT(*) AS track_count,
                   SUM(t.duration_ms) AS total_duration_ms, f.cover_track_id
            FROM tracks t JOIN first_album f ON f.artist_display = t.artist_display AND f.position = 1
            GROUP BY t.artist_display
            ORDER BY MIN(t.artist_unknown), MIN(t.artist_key), MIN(t.id)
        """
        return [
            ArtistSummary(row["artist_display"], row["album_count"], row["track_count"], row["total_duration_ms"],
                          row["cover_track_id"])
            for row in self._db.execute(sql)
        ]

    @_locked
    def genres(self) -> list[GenreSummary]:
        sql = """
            SELECT genre_display, COUNT(*) AS track_count, SUM(duration_ms) AS total_duration_ms
            FROM tracks GROUP BY genre_display
            ORDER BY MIN(genre_unknown), MIN(genre_key), MIN(id)
        """
        return [GenreSummary(*row) for row in self._db.execute(sql)]

    def _one(self, sql: str, param) -> Track | None:
        row = self._db.execute(sql.format(columns=_COLUMNS), (param,)).fetchone()
        return _track(row) if row else None
