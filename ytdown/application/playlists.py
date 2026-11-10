"""Casos de uso de playlists e captura da ordem visível da fila."""

from datetime import datetime, timedelta
from enum import Enum

from ytdown.application.ports import PlaylistRepository
from ytdown.domain.playlist import Playlist
from ytdown.domain.text import search_key


class AutomaticPlaylist(Enum):
    RECENT = 'Adicionadas nos últimos 30 dias'
    MOST_PLAYED = 'Mais tocadas'
    NEVER_PLAYED = 'Nunca tocadas'


class AutomaticPlaylists:
    def __init__(self, tracks, clock=datetime.now):
        self.tracks, self.clock = tracks, clock

    def get(self, kind):
        tracks = self.tracks.list_tracks()
        if kind is AutomaticPlaylist.RECENT:
            now = self.clock()
            tracks = [t for t in tracks if now - timedelta(days=30) <= t.added_at <= now]
            tracks.sort(key=lambda t: t.added_at, reverse=True)
        elif kind is AutomaticPlaylist.MOST_PLAYED:
            tracks = [t for t in tracks if t.play_count > 0]
            tracks.sort(key=lambda t: (-t.play_count, search_key(t.title), t.id or 0))
            tracks = tracks[:50]
        elif kind is AutomaticPlaylist.NEVER_PLAYED:
            tracks = [t for t in tracks if t.play_count == 0]
            tracks.sort(key=lambda t: (search_key(t.title), t.id or 0))
        else:
            raise ValueError('Playlist automática desconhecida')
        return Playlist(kind.value, tuple(tracks))


class ManagePlaylists:
    def __init__(self, playlists: PlaylistRepository):
        self.playlists = playlists

    def create(self, name):
        return self.playlists.create(name)

    def rename(self, playlist_id, name):
        return self.playlists.rename(playlist_id, name)

    def delete(self, playlist_id):
        self.playlists.delete(playlist_id)

    def add_tracks(self, playlist_id, track_ids):
        return self.playlists.add_tracks(playlist_id, track_ids)

    def remove_track(self, playlist_id, index):
        return self.playlists.remove_track(playlist_id, index)

    def move_track(self, playlist_id, source, destination):
        return self.playlists.move_track(playlist_id, source, destination)

    def save_queue(self, name, queue):
        ids = [track.id for track in queue]
        if any(track_id is None for track_id in ids):
            raise ValueError('A fila contém faixa ainda não salva')
        return self.playlists.create(name, ids)
