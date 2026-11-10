"""Casos de uso de playlists e captura da ordem visível da fila."""

from ytdown.application.ports import PlaylistRepository


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
