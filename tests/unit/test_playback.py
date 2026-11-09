"""Caso de uso Playback com o FakeAudioPlayer: toda a lógica do player, sem som."""

import random
import unittest
from datetime import datetime
from pathlib import Path

from tests.fakes import FakeAudioPlayer, FakeLibraryStorage
from ytdown.application.playback import Playback
from ytdown.application.ports import PlayerState
from ytdown.domain.library import Track
from ytdown.domain.play_queue import RESTART_THRESHOLD_MS, RepeatMode

ROOT = Path("C:/Musica/ytDown")


def track(name: str, number: int) -> Track:
    return Track(rel_path=f"Banda/Disco/{name}.mp3", title=name, added_at=datetime(2026, 1, 1),
                 duration_ms=200_000, id=number)


TRACKS = [track(name, i) for i, name in enumerate(["um", "dois", "tres", "quatro"], start=1)]


def path(t: Track) -> Path:
    return ROOT.joinpath(*t.rel_path.split("/"))


class Recorder:
    def __init__(self) -> None:
        self.tracks, self.states, self.positions, self.unavailable = [], [], [], []
        self.queue_changes = 0

    def on_track_changed(self, t):
        self.tracks.append(t)

    def on_state_changed(self, state):
        self.states.append(state)

    def on_position_changed(self, position_ms, duration_ms):
        self.positions.append((position_ms, duration_ms))

    def on_queue_changed(self):
        self.queue_changes += 1

    def on_track_unavailable(self, t, message):
        self.unavailable.append((t, message))


class PlaybackTestCase(unittest.TestCase):
    def setUp(self):
        self.player = FakeAudioPlayer()
        self.playback = Playback(self.player, FakeLibraryStorage(root=ROOT), random.Random(5))
        self.events = Recorder()
        self.playback.add_listener(self.events)

    def assert_playing(self, t: Track):
        self.assertEqual(self.playback.current, t)
        self.assertEqual(self.player.path, path(t))
        self.assertEqual(self.player.state, PlayerState.PLAYING)
        self.assertEqual(self.playback.state, PlayerState.PLAYING)

    def break_file(self, t: Track):
        self.player.broken.add(path(t))


class PlayTests(PlaybackTestCase):
    def test_optional_settings_notifications_and_listener_removal(self):
        snapshots = []

        class SettingsRecorder:
            def on_settings_changed(inner):
                snapshots.append((self.playback.volume, self.playback.muted, self.playback.repeat))

        listener = SettingsRecorder()
        self.playback.add_listener(listener)
        # Recorder legado permanece registrado e não implementa o callback opcional.
        self.playback.set_volume(200)
        self.playback.set_muted(True)
        self.playback.cycle_repeat()
        self.assertEqual(snapshots, [(100, False, RepeatMode.OFF),
                                     (100, True, RepeatMode.OFF),
                                     (100, True, RepeatMode.ALL)])
        self.playback.remove_listener(listener)
        self.playback.remove_listener(listener)
        self.playback.set_volume(-1)
        self.assertEqual(len(snapshots), 3)

    def test_plays_the_list_from_the_chosen_track(self):
        self.playback.play_tracks(TRACKS, start=1)
        self.assert_playing(TRACKS[1])
        self.assertEqual(self.playback.queue, TRACKS)
        self.assertEqual(self.events.tracks, [TRACKS[1]])
        self.assertEqual(self.events.queue_changes, 1)
        self.assertEqual(self.events.states, [PlayerState.PLAYING])

    def test_advances_by_itself_when_a_track_ends(self):
        self.playback.play_tracks(TRACKS)
        self.player.finish()
        self.assert_playing(TRACKS[1])
        self.player.finish()
        self.assert_playing(TRACKS[2])

    def test_stops_at_the_end_of_the_queue(self):
        self.playback.play_tracks(TRACKS, start=3)
        self.player.finish()
        self.assertIsNone(self.playback.current)
        self.assertEqual(self.playback.state, PlayerState.STOPPED)
        self.assertEqual(self.events.tracks[-1], None)

    def test_play_after_the_end_starts_the_queue_over(self):
        self.playback.play_tracks(TRACKS, start=3)
        self.player.finish()
        self.playback.play_pause()
        self.assert_playing(TRACKS[0])

    def test_play_pause_toggles(self):
        self.playback.play_tracks(TRACKS)
        self.playback.play_pause()
        self.assertEqual(self.playback.state, PlayerState.PAUSED)
        self.playback.play_pause()
        self.assert_playing(TRACKS[0])

    def test_after_stop_play_continues_with_the_same_track_without_reloading(self):
        self.playback.play_tracks(TRACKS, start=2)
        self.playback.stop()
        self.assertEqual(self.playback.state, PlayerState.STOPPED)
        loads = len(self.player.loaded)
        self.playback.play_pause()
        self.assert_playing(TRACKS[2])
        self.assertEqual(len(self.player.loaded), loads)

    def test_play_with_an_empty_queue_does_nothing(self):
        self.playback.play_pause()
        self.assertEqual((self.playback.state, self.player.loaded), (PlayerState.STOPPED, []))

    def test_position_and_duration_reach_the_interface(self):
        self.player.durations[path(TRACKS[0])] = 95_000
        self.playback.play_tracks(TRACKS)
        self.player.advance(1500)
        self.assertEqual(self.events.positions[-1], (1500, 95_000))
        self.assertEqual((self.playback.position_ms, self.playback.duration_ms), (1500, 95_000))

    def test_seek_volume_and_mute_go_to_the_player(self):
        self.playback.play_tracks(TRACKS)
        self.playback.seek(42_000)
        self.playback.set_volume(35)
        self.playback.set_muted(True)
        self.assertEqual((self.player.position_ms, self.playback.volume, self.playback.muted), (42_000, 35, True))


class NextPreviousTests(PlaybackTestCase):
    def test_next_and_previous_buttons(self):
        self.playback.play_tracks(TRACKS)
        self.playback.next()
        self.assert_playing(TRACKS[1])
        self.playback.previous()
        self.assert_playing(TRACKS[0])

    def test_next_on_the_last_track_stops(self):
        self.playback.play_tracks(TRACKS, start=3)
        self.playback.next()
        self.assertEqual((self.playback.current, self.playback.state), (None, PlayerState.STOPPED))

    def test_previous_after_three_seconds_restarts_the_track_without_reloading(self):
        self.playback.play_tracks(TRACKS, start=2)
        self.player.advance(RESTART_THRESHOLD_MS + 500)
        loads = len(self.player.loaded)
        self.playback.previous()
        self.assert_playing(TRACKS[2])
        self.assertEqual(self.player.position_ms, 0)
        self.assertEqual(len(self.player.loaded), loads)

    def test_previous_in_the_first_three_seconds_goes_back(self):
        self.playback.play_tracks(TRACKS, start=2)
        self.player.advance(RESTART_THRESHOLD_MS)
        self.playback.previous()
        self.assert_playing(TRACKS[1])

    def test_previous_restarts_a_paused_track_and_plays_it(self):
        self.playback.play_tracks(TRACKS, start=0)
        self.playback.play_pause()
        self.playback.previous()  # Primeira faixa: recomeça.
        self.assert_playing(TRACKS[0])

    def test_previous_with_the_same_song_twice_goes_to_the_other_copy(self):
        self.playback.play_tracks([TRACKS[0], TRACKS[0]], start=1)
        loads = len(self.player.loaded)
        self.playback.previous()
        self.assertEqual(self.playback.current_index, 0)
        self.assertEqual(len(self.player.loaded), loads + 1)


class RepeatAndShuffleTests(PlaybackTestCase):
    def test_repeat_all_starts_over(self):
        self.playback.play_tracks(TRACKS, start=3)
        self.assertEqual(self.playback.cycle_repeat(), RepeatMode.ALL)
        self.player.finish()
        self.assert_playing(TRACKS[0])

    def test_repeat_one_plays_the_same_track_again(self):
        self.playback.play_tracks(TRACKS, start=1)
        self.playback.cycle_repeat()
        self.assertEqual(self.playback.cycle_repeat(), RepeatMode.ONE)
        self.player.finish()
        self.assert_playing(TRACKS[1])
        self.assertEqual(self.player.loaded[-2:], [path(TRACKS[1])] * 2)  # Recomeçou do zero.
        self.playback.next()  # O botão ainda muda de faixa.
        self.assert_playing(TRACKS[2])

    def test_shuffle_keeps_the_current_track_and_plays_every_track_once(self):
        many = [track(f"f{i}", i) for i in range(12)]
        self.playback.play_tracks(many, start=4)
        changes = self.events.queue_changes
        self.playback.set_shuffle(True)
        self.assertTrue(self.playback.shuffle)
        self.assertEqual(self.events.queue_changes, changes + 1)
        self.assert_playing(many[4])
        played = [self.playback.current]
        while self.playback.current is not None:
            self.player.finish()
            played.append(self.playback.current)
        self.assertEqual(sorted(t.id for t in played[:-1]), list(range(12)))
        self.assertNotEqual([t.id for t in played[1:-1]], sorted(t.id for t in played[1:-1]))

    def test_shuffle_with_repeat_all_keeps_playing(self):
        self.playback.play_tracks(TRACKS)
        self.playback.set_shuffle(True)
        self.playback.cycle_repeat()
        played = []
        for _ in range(12):
            self.player.finish()
            played.append(self.playback.current)
        self.assertNotIn(None, played)
        for cycle in (played[3:7], played[7:11]):
            self.assertEqual(sorted(t.id for t in cycle), [1, 2, 3, 4])


class UnavailableTrackTests(PlaybackTestCase):
    def test_missing_file_is_skipped_and_reported(self):
        self.break_file(TRACKS[1])
        self.playback.play_tracks(TRACKS)
        self.player.finish()
        self.assert_playing(TRACKS[2])
        self.assertEqual([t for t, _ in self.events.unavailable], [TRACKS[1]])
        self.assertIn("dois.mp3", self.events.unavailable[0][1])
        self.assertEqual(self.events.tracks[-1], TRACKS[2])  # A interface termina mostrando a que toca.

    def test_choosing_an_unavailable_track_plays_the_next_one(self):
        self.break_file(TRACKS[0])
        self.playback.play_tracks(TRACKS, start=0)
        self.assert_playing(TRACKS[1])
        self.assertEqual(self.player.loaded, [path(TRACKS[0]), path(TRACKS[1])])

    def test_error_while_playing_skips_to_the_next(self):
        self.playback.play_tracks(TRACKS)
        self.player.advance(10_000)
        self.player.fail("Não foi possível tocar \"um.mp3\": o arquivo está corrompido.")
        self.assert_playing(TRACKS[1])
        self.assertEqual(self.events.unavailable[0][0], TRACKS[0])

    def test_unavailable_last_track_stops_the_queue(self):
        self.break_file(TRACKS[3])
        self.playback.play_tracks(TRACKS, start=2)
        self.player.finish()
        self.assertEqual((self.playback.current, self.playback.state), (None, PlayerState.STOPPED))

    def test_with_repeat_one_an_unavailable_track_is_not_retried(self):
        self.break_file(TRACKS[1])
        self.playback.cycle_repeat()
        self.playback.cycle_repeat()  # Repetir uma.
        self.playback.play_tracks(TRACKS, start=1)
        self.assert_playing(TRACKS[2])

    def test_nothing_playable_with_repeat_all_stops_instead_of_looping(self):
        for t in TRACKS:
            self.break_file(t)
        self.playback.cycle_repeat()  # Repetir todas.
        self.playback.play_tracks(TRACKS)
        self.assertEqual(self.playback.state, PlayerState.STOPPED)
        self.assertEqual(sorted(t.id for t, _ in self.events.unavailable), [1, 2, 3, 4])
        self.assertLessEqual(len(self.player.loaded), len(TRACKS))

    def test_a_track_that_plays_resets_the_failure_count(self):
        self.break_file(TRACKS[0])
        self.break_file(TRACKS[2])
        self.playback.cycle_repeat()  # Repetir todas.
        self.playback.play_tracks(TRACKS)  # "um" falha, "dois" toca.
        self.player.advance(1000)
        self.player.finish()  # "tres" falha, "quatro" toca.
        self.assert_playing(TRACKS[3])
        self.player.advance(1000)
        self.player.finish()  # "um" falha de novo, "dois" toca de novo: a fila continua.
        self.assert_playing(TRACKS[1])


class QueueEditTests(PlaybackTestCase):
    def test_append_and_play_next(self):
        extra, soon = track("extra", 10), track("logo", 11)
        self.playback.play_tracks(TRACKS[:2])
        changes = self.events.queue_changes
        self.playback.append([extra])
        self.playback.play_next([soon])
        self.assertEqual(self.playback.queue, [TRACKS[0], soon, TRACKS[1], extra])
        self.assertEqual(self.events.queue_changes, changes + 2)
        self.player.finish()
        self.assert_playing(soon)

    def test_select_plays_a_track_of_the_queue(self):
        self.playback.play_tracks(TRACKS)
        self.playback.select(3)
        self.assert_playing(TRACKS[3])

    def test_removing_the_playing_track_plays_the_next(self):
        self.playback.play_tracks(TRACKS, start=1)
        self.playback.remove(1)
        self.assert_playing(TRACKS[2])
        self.assertEqual(self.playback.queue, [TRACKS[0], TRACKS[2], TRACKS[3]])

    def test_removing_the_paused_track_loads_the_next_without_playing(self):
        self.playback.play_tracks(TRACKS, start=1)
        self.playback.play_pause()
        self.playback.remove(1)
        self.assertEqual((self.playback.current, self.player.path), (TRACKS[2], path(TRACKS[2])))
        self.assertEqual(self.player.state, PlayerState.STOPPED)

    def test_removing_another_track_does_not_interrupt(self):
        self.playback.play_tracks(TRACKS, start=1)
        loads = len(self.player.loaded)
        self.playback.remove(3)
        self.assert_playing(TRACKS[1])
        self.assertEqual(len(self.player.loaded), loads)

    def test_move_changes_what_plays_next(self):
        self.playback.play_tracks(TRACKS)
        self.playback.move(3, 1)
        self.player.finish()
        self.assert_playing(TRACKS[3])

    def test_clear_stops_and_empties(self):
        self.playback.play_tracks(TRACKS)
        self.playback.clear()
        self.assertEqual((self.playback.queue, self.playback.current), ([], None))
        self.assertEqual(self.player.state, PlayerState.STOPPED)
        self.assertIsNone(self.events.tracks[-1])


if __name__ == "__main__":
    unittest.main()
