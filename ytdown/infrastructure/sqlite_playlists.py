"""Persistência de playlists na conexão e trava da biblioteca."""

import sqlite3

from ytdown.domain.playlist import Playlist, playlist_name, playlist_name_key
from ytdown.infrastructure.sqlite_library import _COLUMNS, _track


class SqlitePlaylistRepository:
    def __init__(self, tracks):
        self._tracks = tracks
        self._db = tracks._db
        self._lock = tracks._lock

    def _get(self, playlist_id):
        row = self._db.execute("SELECT id, name FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        if row is None:
            return None
        columns = ', '.join('t.' + c.strip() for c in _COLUMNS.split(','))
        rows = self._db.execute(f"SELECT {columns} FROM playlist_tracks p JOIN tracks t ON t.id = p.track_id WHERE p.playlist_id = ? ORDER BY p.position", (playlist_id,))
        return Playlist(row['name'], tuple(_track(r) for r in rows), row['id'])

    def get(self, playlist_id):
        with self._lock:
            return self._get(playlist_id)

    def list_playlists(self):
        with self._lock:
            ids = [r[0] for r in self._db.execute('SELECT id FROM playlists ORDER BY name_key, id')]
            return [self._get(i) for i in ids]

    def _write(self, operation):
        with self._lock:
            try:
                self._db.execute('BEGIN IMMEDIATE')
                result = operation()
                self._db.commit()
                return result
            except sqlite3.IntegrityError as exc:
                self._db.rollback()
                raise ValueError('Nome de playlist duplicado ou faixa inexistente') from exc
            except Exception:
                self._db.rollback()
                raise

    def _require(self, playlist_id):
        playlist = self._get(playlist_id)
        if playlist is None:
            raise KeyError(playlist_id)
        return playlist

    def _replace(self, playlist_id, ids):
        self._db.execute('DELETE FROM playlist_tracks WHERE playlist_id = ?', (playlist_id,))
        self._db.executemany('INSERT INTO playlist_tracks VALUES (?, ?, ?)',
                             ((playlist_id, i, track_id) for i, track_id in enumerate(ids)))

    def create(self, name, track_ids=()):
        name, ids = playlist_name(name), tuple(track_ids)
        def write():
            cursor = self._db.execute('INSERT INTO playlists(name, name_key) VALUES (?, ?)', (name, playlist_name_key(name)))
            self._replace(cursor.lastrowid, ids)
            return self._require(cursor.lastrowid)
        return self._write(write)

    def rename(self, playlist_id, name):
        name = playlist_name(name)
        def write():
            self._require(playlist_id)
            self._db.execute('UPDATE playlists SET name = ?, name_key = ? WHERE id = ?', (name, playlist_name_key(name), playlist_id))
            return self._require(playlist_id)
        return self._write(write)

    def delete(self, playlist_id):
        def write():
            self._require(playlist_id)
            self._db.execute('DELETE FROM playlists WHERE id = ?', (playlist_id,))
        self._write(write)

    def _edit(self, playlist_id, edit):
        def write():
            ids = [track.id for track in self._require(playlist_id).tracks]
            edit(ids)
            self._replace(playlist_id, ids)
            return self._require(playlist_id)
        return self._write(write)

    def add_tracks(self, playlist_id, track_ids):
        ids = tuple(track_ids)
        return self._edit(playlist_id, lambda current: current.extend(ids))

    def remove_track(self, playlist_id, index):
        def edit(ids):
            if not 0 <= index < len(ids):
                raise IndexError(index)
            ids.pop(index)
        return self._edit(playlist_id, edit)

    def move_track(self, playlist_id, source, destination):
        def edit(ids):
            if not 0 <= source < len(ids) or not 0 <= destination < len(ids):
                raise IndexError((source, destination))
            ids.insert(destination, ids.pop(source))
        return self._edit(playlist_id, edit)
