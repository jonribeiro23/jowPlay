"""Persistência entre sessões, com janela Qt offscreen e player controlável."""
import json
import tempfile
import unittest
import wave
from datetime import datetime
from pathlib import Path

from tests.qt_support import dispose, qt_app, wait_until
from tests.fakes import FakeAudioPlayer, FakeLibraryStorage, InMemoryTrackRepository
from ytdown.application.playback import Playback
from ytdown.application.ports import PlayerState
from ytdown.domain.library import Track
from ytdown.infrastructure.json_settings import JsonSettings
from ytdown.presentation.qt.main_window import MainWindow
from ytdown.presentation.qt.pages import PageId
from ytdown.infrastructure.qt_audio_player import QtAudioPlayer


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_roundtrip_and_queue_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            settings = JsonSettings(path)
            settings.set('unrelated', {'value': 4})
            repo, storage = InMemoryTrackRepository(), FakeLibraryStorage()
            tracks = [repo.add(Track(rel_path=f'{i}.mp3', title=str(i), added_at=datetime.now())) for i in range(3)]
            storage.files = {track.rel_path: b'audio' for track in tracks}
            player = FakeAudioPlayer()
            playback = Playback(player, storage, tracks=repo)
            first = MainWindow(settings=settings)
            first.show()
            first.show_page(PageId.ALBUMS)
            first.splitter.setSizes([250, 600, 350])
            playback.play_tracks([tracks[0], tracks[1], tracks[0], tracks[2]], 2)
            playback.set_shuffle(True)
            playback.cycle_repeat()
            playback.set_volume(37)
            playback.set_muted(True)
            playback.seek(12345)
            state = playback.workspace_state()
            first.closing.connect(lambda: settings.set('workspace.playback', playback.workspace_state()))
            first.closing.connect(playback.stop)
            dispose(first)
            self.assertEqual(settings.get('workspace.playback'), state)

            saved = JsonSettings(path)
            second = MainWindow(settings=saved)
            self.assertEqual(second.current_page(), PageId.ALBUMS)
            restored = Playback(FakeAudioPlayer(), storage, tracks=repo)
            restored.restore_workspace(saved.get('workspace.playback'), repo)
            self.assertEqual(restored.workspace_state(), state)
            self.assertEqual(restored.state, PlayerState.STOPPED)
            restored.play_pause()
            self.assertEqual(restored.position_ms, 12345)
            self.assertEqual(restored.state, PlayerState.PLAYING)
            expected = restored.upcoming()
            if expected:
                restored.next()
                self.assertEqual(restored.current, expected[0])
            self.assertEqual(saved.get('unrelated'), {'value': 4})
            dispose(second)

    def test_corrupt_and_invalid_values_and_missing_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_bytes(b'\xff{')
            settings = JsonSettings(path)
            window = MainWindow(settings=settings)
            repo, storage = InMemoryTrackRepository(), FakeLibraryStorage()
            track = repo.add(Track(rel_path='a.mp3', title='a', added_at=datetime.now()))
            storage.files[track.rel_path] = b'audio'
            playback = Playback(FakeAudioPlayer(), storage, tracks=repo)
            playback.restore_workspace({'volume': True, 'muted': 3, 'repeat': [], 'shuffle': 'yes',
                'queue': [track.id, 999, track.id], 'current': 2, 'order': [2, 1, 0], 'position': -1}, repo)
            self.assertEqual(playback.queue, [track, track])
            self.assertEqual(playback.current_index, 1)
            self.assertEqual(playback.position_ms, 0)
            self.assertEqual(playback.volume, 80)
            storage.files.clear()
            playback.restore_workspace({'queue': [track.id], 'current': 0}, repo)
            self.assertEqual(playback.queue, [])
            dispose(window)
            json.loads(path.read_text(encoding='utf-8'))

    def test_real_qt_deferred_seek_and_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audio.wav'
            with wave.open(str(path), 'wb') as audio:
                audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                audio.writeframes(b'\0\0' * 8000 * 5)
            storage, repo = FakeLibraryStorage(root=Path(directory)), InMemoryTrackRepository()
            track = repo.add(Track(rel_path=path.name, title='audio', added_at=datetime.now()))
            storage.files[path.name] = b'present'
            player = QtAudioPlayer()
            player.set_muted(True)
            playback = Playback(player, storage, tracks=repo)
            try:
                playback.restore_workspace({'queue': [track.id], 'current': 0, 'position': 2000}, repo)
                self.assertEqual(playback.state, PlayerState.STOPPED)
                self.assertTrue(wait_until(lambda: player.duration_ms > 0 and abs(player.position_ms - 2000) < 200))
                playback.play_pause()
                self.assertTrue(wait_until(lambda: player.position_ms >= 2000))
                self.assertEqual(playback.state, PlayerState.PLAYING)
            finally:
                player.shutdown()

    def test_composed_window_saves_before_stop_and_reopens(self):
        from ytdown.bootstrap import build_library, build_main_window, build_extract_batch
        from ytdown.presentation.qt.send_dialog import PhoneSharing
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = build_library(root / 'library.db', root / 'settings.json', root / 'music')
            try:
                library.storage.root.mkdir(parents=True, exist_ok=True)
                (library.storage.root / 'a.mp3').write_bytes(b'audio')
                track = library.tracks.add(Track(rel_path='a.mp3', title='a', added_at=datetime.now()))
                playback = Playback(FakeAudioPlayer(), library.storage, tracks=library.tracks)
                window = build_main_window(library, playback, build_extract_batch(), PhoneSharing(lambda callback: None))
                playback.play_tracks([track, track], 1)
                playback.seek(4200)
                dispose(window)
                self.assertEqual(library.settings.get('workspace.playback')['position'], 4200)
                restored = Playback(FakeAudioPlayer(), library.storage, tracks=library.tracks)
                window = build_main_window(library, restored, build_extract_batch(), PhoneSharing(lambda callback: None))
                self.assertEqual(restored.current_index, 1)
                self.assertEqual(restored.position_ms, 4200)
                self.assertEqual(restored.state, PlayerState.STOPPED)
                dispose(window)
            finally:
                library.close()
