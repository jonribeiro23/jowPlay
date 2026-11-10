import unittest
from datetime import datetime
from dataclasses import replace

from tests.fakes import FakeAudioPlayer, FakeLibraryStorage, InMemoryTrackRepository
from ytdown.application.playback import Playback
from ytdown.domain.library import Track


class ListeningTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.repo = InMemoryTrackRepository()
        self.track = self.repo.add(Track('a.mp3', 'A', datetime(2020, 1, 1), duration_ms=600_000))
        self.player = FakeAudioPlayer()
        self.player.durations = {FakeLibraryStorage().absolute('a.mp3'): 600_000}
        self.playback = Playback(self.player, FakeLibraryStorage(), tracks=self.repo,
                                 clock=lambda: self.now, wall_clock=lambda: datetime(2026, 1, 1))

    def advance(self, ms):
        self.now += ms / 1000
        self.player.advance(ms)

    def test_skip_seek_pause_and_repeat(self):
        self.playback.play_tracks([self.track])
        self.advance(30_000)
        self.playback.next()
        self.assertEqual(self.repo.get(self.track.id).play_count, 0)
        self.playback.play_tracks([self.track])
        self.playback.seek(300_000)
        self.advance(120_000)
        self.playback.play_pause()
        self.now += 500
        self.playback.play_pause()
        self.playback.seek(100_000)
        self.advance(120_000)
        self.assertEqual(self.repo.get(self.track.id).play_count, 1)
        self.playback.play_tracks([self.track])
        self.advance(240_000)
        self.assertEqual(self.repo.get(self.track.id).play_count, 2)

    def test_half_and_concurrent_edit(self):
        self.player.durations = {FakeLibraryStorage().absolute('a.mp3'): 100_000}
        self.playback.play_tracks([self.track])
        self.repo.update(replace(self.track, title='Editada'))
        self.advance(50_000)
        saved = self.repo.get(self.track.id)
        self.assertEqual((saved.title, saved.play_count, saved.last_played_at),
                         ('Editada', 1, datetime(2026, 1, 1)))

    def test_late_duration_qualifies_accumulated_listening(self):
        self.player.durations = {FakeLibraryStorage().absolute('a.mp3'): 0}
        self.track = replace(self.track, duration_ms=0)
        self.repo.update(self.track)
        self.playback.play_tracks([self.track])
        self.advance(50_000)
        self.assertEqual(self.repo.get(self.track.id).play_count, 0)
        self.playback.on_duration(100_000)
        self.assertEqual(self.repo.get(self.track.id).play_count, 1)
