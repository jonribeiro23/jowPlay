import unittest
from datetime import datetime

from ytdown.domain.library import Track
from ytdown.domain.playlist import Playlist, playlist_name_key


class PlaylistTests(unittest.TestCase):
    def test_name_unicode_and_validation(self):
        self.assertEqual(playlist_name_key('  STRASSE  '), playlist_name_key('Straße'))
        self.assertEqual(playlist_name_key('E\u0301'), playlist_name_key('é'))
        with self.assertRaises(ValueError):
            Playlist('  ')

    def test_repetitions_contribute_to_duration(self):
        track = Track('a', 'a', datetime.now(), duration_ms=42)
        playlist = Playlist('  Música ', (track, track))
        self.assertEqual((playlist.name, playlist.duration_ms, len(playlist.tracks)), ('Música', 84, 2))
