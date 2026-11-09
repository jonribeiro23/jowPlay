"""Playback com o player de verdade (QtAudioPlayer), no mudo: os avisos do Qt chegam de forma
assíncrona, diferente do dublê, e o caso de uso precisa funcionar igual.
"""

import random
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tests.qt_support import qt_app, wait_until
from PySide6.QtCore import QObject
from PySide6.QtMultimedia import QMediaDevices

from tests.fakes import FakeLibraryStorage
from ytdown.application.playback import Playback
from ytdown.application.ports import PlayerState
from ytdown.domain.library import Track
from ytdown.infrastructure.qt_audio_player import QtAudioPlayer


class Recorder:
    def __init__(self):
        self.tracks, self.unavailable = [], []

    def on_track_changed(self, track):
        self.tracks.append(track.title if track else None)

    def on_state_changed(self, state): ...

    def on_position_changed(self, position_ms, duration_ms): ...

    def on_queue_changed(self): ...

    def on_track_unavailable(self, track, message):
        self.unavailable.append(track.title)


@unittest.skipUnless(shutil.which("ffmpeg"), "precisa do ffmpeg para criar os arquivos")
class PlaybackWithQtPlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()
        if not QMediaDevices.audioOutputs():
            raise unittest.SkipTest("sem saída de áudio neste computador")

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in ("primeira", "terceira"):
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "0.6",
                            str(self.root / f"{name}.wav")], check=True)
        self.owner = QObject()
        self.player = QtAudioPlayer(self.owner)
        self.player.set_muted(True)  # Sem barulho.
        self.addCleanup(self.owner.deleteLater)
        self.addCleanup(self.player.shutdown)
        self.playback = Playback(self.player, FakeLibraryStorage(root=self.root), random.Random(1))
        self.events = Recorder()
        self.playback.add_listener(self.events)

    def tracks(self, *names):
        return [Track(rel_path=f"{name}.wav", title=name, added_at=datetime(2026, 1, 1), id=i)
                for i, name in enumerate(names, start=1)]

    def test_plays_the_queue_skipping_a_missing_file_and_stops_at_the_end(self):
        self.playback.play_tracks(self.tracks("primeira", "sumiu", "terceira"))
        self.assertTrue(wait_until(lambda: self.playback.current is None, 8000), self.events.tracks)
        self.assertEqual(self.events.tracks, ["primeira", "sumiu", "terceira", None])
        self.assertEqual(self.events.unavailable, ["sumiu"])
        self.assertEqual(self.playback.state, PlayerState.STOPPED)

    def test_repeat_one_plays_the_track_again_with_the_real_player(self):
        self.playback.cycle_repeat()
        self.playback.cycle_repeat()  # Repetir uma.
        self.playback.play_tracks(self.tracks("primeira", "terceira"))
        self.assertTrue(wait_until(lambda: self.events.tracks.count("primeira") >= 3, 8000), self.events.tracks)
        self.assertNotIn("terceira", self.events.tracks)
        self.playback.stop()


if __name__ == "__main__":
    unittest.main()
