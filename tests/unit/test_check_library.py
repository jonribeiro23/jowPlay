"""Integridade da biblioteca: ausência no disco vira estado persistido, não exclusão."""

import unittest
from datetime import datetime
from threading import Event

from tests.fakes import FakeLibraryStorage, InMemoryTrackRepository
from ytdown.application.library import CheckLibrary, RemoveUnavailableTracks
from ytdown.application.playback import Playback
from ytdown.domain.library import Track
from tests.fakes import FakeAudioPlayer


class CheckLibraryTests(unittest.TestCase):
    def setUp(self):
        self.storage = FakeLibraryStorage()
        self.tracks = InMemoryTrackRepository()
        self.first = self.tracks.add(Track("a.mp3", "A", datetime.now()))
        self.second = self.tracks.add(Track("b.mp3", "B", datetime.now(), missing=True))

    def test_marks_missing_and_restores_when_file_returns(self):
        check = CheckLibrary(self.storage, self.tracks)
        result = check()
        self.assertEqual((result.checked, result.changed), (2, 1))
        self.assertTrue(self.tracks.get(self.first.id).missing)
        self.assertTrue(self.tracks.get(self.second.id).missing)
        self.storage.files["a.mp3"] = b"a"
        self.assertEqual(check().changed, 1)
        self.assertFalse(self.tracks.get(self.first.id).missing)

    def test_unavailable_root_does_not_mark_every_track_missing(self):
        self.storage.available = False
        result = CheckLibrary(self.storage, self.tracks)()
        self.assertFalse(result.root_available)
        self.assertEqual(result.changed, 0)
        self.assertFalse(self.tracks.get(self.first.id).missing)
        self.assertTrue(self.tracks.get(self.second.id).missing)

    def test_cancel_keeps_unchecked_tracks_unchanged(self):
        cancel = Event()
        cancel.set()
        result = CheckLibrary(self.storage, self.tracks)(cancel)
        self.assertTrue(result.cancelled)
        self.assertFalse(self.tracks.get(self.first.id).missing)

    def test_removal_rechecks_the_file_and_keeps_restored_track(self):
        removed = RemoveUnavailableTracks(self.storage, self.tracks)()
        self.assertEqual(removed, {self.second.id})
        self.assertIsNone(self.tracks.get(self.second.id))
        self.storage.files["a.mp3"] = b"a"
        self.tracks.update(Track("a.mp3", "A", datetime.now(), missing=True, id=self.first.id))
        self.assertEqual(RemoveUnavailableTracks(self.storage, self.tracks)(), set())
        self.assertFalse(self.tracks.get(self.first.id).missing)

    def test_player_purges_all_removed_copies(self):
        player = FakeAudioPlayer()
        playback = Playback(player, self.storage)
        missing = Track("gone.mp3", "Gone", datetime.now(), missing=True, id=99)
        playback.play_tracks([self.first, missing, self.first], 1)
        self.assertEqual(playback.queue, [self.first, missing, self.first])
        playback.remove_tracks({self.first.id})
        self.assertEqual(playback.queue, [missing])


if __name__ == "__main__":
    unittest.main()
