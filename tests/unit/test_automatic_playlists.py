import unittest
from datetime import datetime, timedelta

from ytdown.application.playlists import AutomaticPlaylist, AutomaticPlaylists
from ytdown.domain.library import Track
from tests.fakes import InMemoryTrackRepository


class AutomaticPlaylistsTests(unittest.TestCase):
    def test_boundaries_ranking_and_never_played(self):
        now = datetime(2025, 5, 1, 12)
        repo = InMemoryTrackRepository()
        edge = repo.add(Track('edge', 'edge', now - timedelta(days=30)))
        repo.add(Track('old', 'old', now - timedelta(days=30, microseconds=1)))
        repo.add(Track('future', 'future', now + timedelta(microseconds=1)))
        for i in range(55):
            repo.add(Track(str(i), f'{i:02}', now, play_count=i + 1))
        automatic = AutomaticPlaylists(repo, lambda: now)
        recent = automatic.get(AutomaticPlaylist.RECENT).tracks
        self.assertIn(edge, recent)
        self.assertEqual(len(recent), 56)
        top = automatic.get(AutomaticPlaylist.MOST_PLAYED).tracks
        self.assertEqual(len(top), 50)
        self.assertEqual([t.play_count for t in top], list(range(55, 5, -1)))
        self.assertEqual({t.title for t in automatic.get(AutomaticPlaylist.NEVER_PLAYED).tracks},
                         {'edge', 'old', 'future'})
