"""QtAudioPlayer com arquivos reais de cada formato, criados com o ffmpeg.

Toca de verdade, mas sempre no mudo: o teste não faz barulho no computador de quem roda.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.qt_support import pause, qt_app, wait_until
from PySide6.QtCore import QObject
from PySide6.QtMultimedia import QMediaDevices, QMediaPlayer

from tests.fakes import FakeAudioPlayer
from ytdown.application.ports import AudioPlayer, PlayerListener, PlayerState
from ytdown.infrastructure.qt_audio_player import QtAudioPlayer, perceived_to_linear

# Formato -> (opções do ffmpeg, duração em segundos). Durações diferentes identificam a faixa.
FORMATS = {
    "mp3": (["-c:a", "libmp3lame"], 1.5),
    "m4a": (["-c:a", "aac"], 1.7),
    "flac": (["-c:a", "flac"], 1.9),
    "wav": (["-c:a", "pcm_s16le"], 2.1),
}
TOLERANCE_MS = 150


class Recorder:
    """PlayerListener que anota tudo o que o player avisa."""

    def __init__(self) -> None:
        self.positions, self.durations, self.states, self.errors = [], [], [], []
        self.finished = 0

    def on_position(self, position_ms):
        self.positions.append(position_ms)

    def on_duration(self, duration_ms):
        self.durations.append(duration_ms)

    def on_state(self, state):
        self.states.append(state)

    def on_finished(self):
        self.finished += 1

    def on_error(self, message):
        self.errors.append(message)


@unittest.skipUnless(shutil.which("ffmpeg"), "precisa do ffmpeg para criar os arquivos")
class QtAudioPlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()
        if not QMediaDevices.audioOutputs():
            raise unittest.SkipTest("sem saída de áudio neste computador")
        cls.temp = tempfile.TemporaryDirectory()
        cls.files = {}
        for extension, (codec, seconds) in FORMATS.items():
            path = Path(cls.temp.name) / f"tom.{extension}"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                            "-t", str(seconds), *codec, str(path)], check=True)
            cls.files[extension] = path

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.owner = QObject()
        self.player = QtAudioPlayer(self.owner)
        self.player.set_muted(True)  # Sem barulho.
        self.events = Recorder()
        self.player.set_listener(self.events)
        self.addCleanup(self.owner.deleteLater)
        self.addCleanup(self.player.shutdown)

    def load_and_wait(self, path):
        self.player.load(path)
        self.assertTrue(wait_until(lambda: self.player.duration_ms > 0, 5000), f"{path.name} não carregou")

    # --- cada formato

    def test_each_format_plays_seeks_and_reports_the_end(self):
        for extension, (_, seconds) in FORMATS.items():
            with self.subTest(extension):
                self.events.__init__()
                path = self.files[extension]
                self.load_and_wait(path)
                self.assertAlmostEqual(self.player.duration_ms, seconds * 1000, delta=TOLERANCE_MS)
                self.assertEqual(self.player.state, PlayerState.STOPPED)

                self.player.play()
                self.assertTrue(wait_until(lambda: self.player.position_ms > 100, 3000), "não andou")
                self.assertEqual(self.player.state, PlayerState.PLAYING)

                target = int(seconds * 1000) - 500
                self.player.seek(target)
                self.assertTrue(wait_until(lambda: self.player.position_ms >= target, 2000), "o seek falhou")

                self.assertTrue(wait_until(lambda: self.events.finished == 1, 3000), "não avisou o fim")
                self.assertEqual(self.player.state, PlayerState.STOPPED)
                self.assertEqual(self.events.states[0], PlayerState.PLAYING)
                self.assertEqual(self.events.states[-1], PlayerState.STOPPED)
                self.assertTrue(self.events.positions)
                self.assertEqual(self.events.errors, [])

    def test_pause_keeps_the_position_and_play_resumes(self):
        self.load_and_wait(self.files["wav"])
        self.player.play()
        self.assertTrue(wait_until(lambda: self.player.position_ms > 300, 3000))
        self.player.pause()
        self.assertTrue(wait_until(lambda: self.player.state is PlayerState.PAUSED, 1000))
        paused_at = self.player.position_ms
        pause(300)
        self.assertAlmostEqual(self.player.position_ms, paused_at, delta=30)
        self.player.play()
        self.assertTrue(wait_until(lambda: self.player.position_ms > paused_at + 100, 2000))

    def test_stop_goes_back_to_the_beginning_without_reporting_the_end(self):
        self.load_and_wait(self.files["mp3"])
        self.player.play()
        self.assertTrue(wait_until(lambda: self.player.position_ms > 200, 3000))
        self.player.stop()
        self.assertTrue(wait_until(lambda: self.player.state is PlayerState.STOPPED, 1000))
        self.assertEqual(self.player.position_ms, 0)
        pause(300)
        self.assertEqual(self.events.finished, 0)

    # --- erros

    def test_missing_file_is_reported_and_the_player_keeps_working(self):
        missing = Path(self.temp.name) / "sumiu.mp3"
        self.player.load(missing)
        self.assertEqual(len(self.events.errors), 1)
        self.assertIn("sumiu.mp3", self.events.errors[0])
        self.assertIn("não foi encontrado", self.events.errors[0])
        self.player.play()  # Sem arquivo, não faz nada (nem falha).
        self.assertEqual(self.player.state, PlayerState.STOPPED)
        self.assertIsNone(self.player.source)

        self.load_and_wait(self.files["mp3"])
        self.player.play()
        self.assertTrue(wait_until(lambda: self.player.position_ms > 100, 3000))

    def test_corrupted_file_is_reported_and_the_player_keeps_working(self):
        broken = Path(self.temp.name) / "quebrado.mp3"
        broken.write_bytes(b"isto nao e audio" * 500)
        self.player.load(broken)
        self.player.play()
        self.assertTrue(wait_until(lambda: self.events.errors, 5000), "não avisou o erro")
        self.assertIn("quebrado.mp3", self.events.errors[0])
        self.assertIn("corrompido", self.events.errors[0])
        self.assertEqual(self.player.state, PlayerState.STOPPED)

        self.load_and_wait(self.files["flac"])
        self.player.play()
        self.assertTrue(wait_until(lambda: self.player.position_ms > 100, 3000))

    # --- troca rápida

    def test_switching_tracks_quickly_leaves_only_the_last_one_playing(self):
        order = list(self.files.values()) * 5  # 20 trocas seguidas, sem esperar nada.
        for path in order:
            self.player.load(path)
            self.player.play()
        last = order[-1]
        self.assertEqual(self.player.source, last)
        self.assertTrue(wait_until(lambda: self.player.position_ms > 200, 5000))
        self.assertEqual(self.player.state, PlayerState.PLAYING)
        self.assertAlmostEqual(self.player.duration_ms, FORMATS[last.suffix[1:]][1] * 1000, delta=TOLERANCE_MS)
        # Um único QMediaPlayer para todas as faixas: não há como duas tocarem juntas.
        self.assertEqual(len(self.owner.findChildren(QMediaPlayer)), 1)

        self.player.seek(self.player.duration_ms - 300)
        self.assertTrue(wait_until(lambda: self.events.finished >= 1, 3000))
        pause(300)
        self.assertEqual(self.events.finished, 1)  # Só a última terminou; as trocadas não avisam fim.
        self.assertEqual(self.events.errors, [])

    # --- volume e arquivo

    def test_volume_follows_the_ear_and_mute_is_separate(self):
        self.player.set_volume(50)
        self.assertEqual(self.player.volume, 50)
        self.assertAlmostEqual(self.player._output.volume(), perceived_to_linear(50), places=3)
        self.assertLess(perceived_to_linear(50), 0.5)  # O meio do controle é bem menos que metade da amplitude.
        self.player.set_volume(150)
        self.assertEqual(self.player.volume, 100)
        self.player.set_muted(False)
        self.assertFalse(self.player.muted)
        self.player.set_muted(True)
        self.assertTrue(self.player.muted)
        self.assertEqual(self.player.volume, 100)  # Mudo não mexe no volume.

    def test_shutdown_releases_the_file(self):
        copy = Path(self.temp.name) / "copia.wav"
        shutil.copy(self.files["wav"], copy)
        self.load_and_wait(copy)
        self.player.play()
        self.assertTrue(wait_until(lambda: self.player.position_ms > 100, 3000))
        self.player.shutdown()
        pause(200)
        copy.unlink()  # No Windows, falharia se o arquivo ainda estivesse aberto.
        self.assertFalse(copy.exists())


class PortTests(unittest.TestCase):
    def test_real_player_and_test_double_have_everything_the_port_asks_for(self):
        members = [name for name in vars(AudioPlayer) if not name.startswith("_")]
        listener = [name for name in vars(PlayerListener) if not name.startswith("_")]
        self.assertIn("load", members)
        # A classe real (propriedades) e uma instância do dublê (lá, volume e mudo são atributos).
        for implementation in (QtAudioPlayer, FakeAudioPlayer()):
            with self.subTest(type(implementation).__name__):
                self.assertEqual([name for name in members if not hasattr(implementation, name)], [])
        self.assertEqual([name for name in listener if not hasattr(Recorder, name)], [])


if __name__ == "__main__":
    unittest.main()
