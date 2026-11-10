"""JOW-28: comandos, sincronização e capas na composição real, sem som."""

import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from tests.qt_support import dispose, pause, qt_app, wait_until
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtTest import QTest

from tests.fakes import FakeAudioPlayer, FakeCovers, FakeDownloader, FakeTags
from ytdown.application.extraction import ExtractAudio, ExtractBatch
from ytdown.application.playback import Playback
from ytdown.application.ports import PlayerState
from ytdown.bootstrap import build_library, build_main_window
from ytdown.domain.library import Track
from ytdown.domain.play_queue import RepeatMode
from ytdown.presentation.qt.pages import PageId
from ytdown.presentation.qt.send_dialog import PhoneSharing
from ytdown.presentation.qt.transport_bar import TransportBar


def cover_bytes():
    image = QImage(12, 12, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        library = build_library(root / 'db', root / 'settings', root / 'music')
        self.addCleanup(library.close)
        for i in range(3):
            library.tracks.add(Track(f'{i}.mp3', f'Título {i}', datetime.now(),
                                     artist=f'Artista {i}', duration_ms=180_000))
        self.player = FakeAudioPlayer()
        self.playback = Playback(self.player, library.storage)
        covers = FakeCovers()
        batch = ExtractBatch(ExtractAudio(FakeDownloader(), covers, FakeTags()), covers)
        self.window = build_main_window(library, self.playback, batch, PhoneSharing(lambda cb: None))
        self.addCleanup(dispose, self.window)
        self.window.show()
        self.bar = self.window.transport
        self.songs = self.window.page(PageId.SONGS)

    def play_from_songs(self):
        self.songs.table.setCurrentIndex(self.songs.model.index(0, 0))
        QTest.keyClick(self.songs.table, Qt.Key.Key_Return)

    def test_now_playing_access_history_and_compact(self):
        page = self.window.page(PageId.NOW_PLAYING)
        compact = self.window.compact_player
        self.window.navigation.select(PageId.NOW_PLAYING)
        self.assertEqual(self.window.current_page(), PageId.NOW_PLAYING)
        self.window.back_button.click()
        self.assertEqual(self.window.current_page(), PageId.SONGS)
        self.bar.now_playing_button.click()
        self.assertEqual(self.window.current_page(), PageId.NOW_PLAYING)
        self.window.back_button.click()
        QTest.mouseDClick(self.bar.cover, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.current_page(), PageId.NOW_PLAYING)
        self.play_from_songs()
        self.assertEqual(page.title.text(), 'Título 0')
        self.assertEqual(page.upcoming.count(), 2)
        page.compact_button.click()
        self.assertTrue(compact.isVisible())
        self.assertTrue(compact.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        compact.next.click()
        self.assertEqual(page.title.text(), 'Título 1')
        self.assertEqual(compact.title.text(), 'Título 1')
        compact.play.click()
        self.assertEqual(self.player.state, PlayerState.PAUSED)
        self.playback.play_pause()
        self.assertEqual(compact.play.text(), '⏸')
        compact.move(123, 234)
        compact.close()
        self.assertEqual(self.window.settings.get(compact.POSITION_KEY), [123, 234])
        from ytdown.presentation.qt.now_playing import CompactPlayer
        other = CompactPlayer(self.playback, page, self.window.settings, self.window)
        self.assertEqual((other.x(), other.y()), (123, 234))
        other.shutdown()
        other.deleteLater()

    def test_now_playing_cover_loading_is_async_and_shutdown_unsubscribes(self):
        from ytdown.presentation.qt.now_playing import NowPlayingPage
        started, release = threading.Event(), threading.Event()
        def slow_cover(track):
            started.set()
            release.wait(3)
            return cover_bytes()
        page = NowPlayingPage(self.playback, slow_cover, QPixmap())
        try:
            tracks = self.songs.model.tracks
            self.playback.play_tracks(tracks)
            self.assertTrue(started.wait(1))
            self.playback.next()
            self.assertEqual(page.title.text(), tracks[1].title)
            listener = page._listener
            page.shutdown()
            self.assertNotIn(listener, self.playback._listeners)
        finally:
            release.set()
            page.deleteLater()

    def test_window_waits_for_transport_cover_reader(self):
        started, release = threading.Event(), threading.Event()
        def slow_cover(track):
            started.set()
            release.wait(5)
            return None
        bar = TransportBar()
        bar.bind(self.playback, read_cover=slow_cover)
        self.window.background_jobs.append(bar)
        finished = []
        self.window.closing.connect(lambda: finished.append(True))
        try:
            self.playback.play_tracks(self.songs.model.tracks)
            self.assertTrue(started.wait(1))
            self.window.close()
            self.assertEqual(finished, [])
            release.set()
            self.assertTrue(wait_until(lambda: bool(finished)))
            self.assertFalse(bar._worker.is_alive())
        finally:
            release.set()
            bar.deleteLater()

    def test_songs_transport_and_external_playback(self):
        self.assertFalse(self.bar.cover.pixmap().isNull())
        self.play_from_songs()
        self.assertEqual(self.player.state, PlayerState.PLAYING)
        self.assertEqual(self.bar.now_playing.text(), 'Título 0')
        self.assertEqual(self.bar.artist.text(), 'Artista 0')
        self.assertEqual(self.bar.play_button.toolTip(), 'Pausar')
        self.bar.play_button.click()
        self.assertEqual(self.player.state, PlayerState.PAUSED)
        self.playback.play_pause()
        self.assertEqual(self.bar.play_button.toolTip(), 'Pausar')
        self.bar.next_button.click()
        self.assertEqual(self.bar.now_playing.text(), 'Título 1')
        self.bar.previous_button.click()
        self.assertEqual(self.bar.now_playing.text(), 'Título 0')
        self.player.advance(12_000)
        self.assertEqual(self.bar.time_label.text(), '0:12 / 3:00')
        self.bar.previous_button.click()
        self.assertEqual(self.player.position_ms, 0)
        self.playback.select(2)
        self.assertEqual(self.bar.artist.text(), 'Artista 2')
        self.player.advance(20_000)
        self.playback.stop()
        self.assertEqual(self.bar.time_label.text(), '0:00 / 3:00')
        self.playback.clear()
        self.assertEqual(self.bar.now_playing.text(), 'Nada tocando')
        self.assertEqual(self.bar.time_label.text(), '0:00 / 0:00')
        self.assertFalse(self.bar.position.isEnabled())

    def test_settings_commands_and_external_clamped_values(self):
        self.bar.volume.setValue(23)
        self.assertEqual(self.player.volume, 23)
        self.playback.set_volume(999)
        self.assertEqual(self.bar.volume.value(), self.player.volume)
        self.assertEqual(self.bar.volume.value(), 100)
        self.playback.set_volume(-20)
        self.assertEqual(self.bar.volume.value(), 0)
        self.bar.mute_button.click()
        self.assertTrue(self.player.muted)
        self.playback.set_muted(False)
        self.assertFalse(self.bar.mute_button.isChecked())
        self.bar.shuffle_button.click()
        self.assertTrue(self.playback.shuffle)
        self.playback.set_shuffle(False)
        self.assertFalse(self.bar.shuffle_button.isChecked())
        for mode in (RepeatMode.ALL, RepeatMode.ONE, RepeatMode.OFF):
            self.bar.repeat_button.click()
            self.assertEqual(self.playback.repeat, mode)
            self.assertEqual(self.bar.repeat_button.isChecked(), mode is not RepeatMode.OFF)
        self.playback.cycle_repeat()
        self.assertEqual(self.bar.repeat_button.toolTip(), 'Repetir: todas')
        self.playback.cycle_repeat()
        self.assertEqual(self.bar.repeat_button.text(), '1')

    def test_drag_clock_release_single_seek_and_keyboard(self):
        self.play_from_songs()
        self.player.seek = Mock(wraps=self.player.seek)
        slider = self.bar.position
        slider.setSliderDown(True)
        slider.setValue(65_000)
        self.player.advance(2_000)
        self.assertEqual(slider.value(), 65_000)
        self.assertEqual(self.bar.time_label.text(), '1:05 / 3:00')
        self.player.seek.assert_not_called()
        slider.setSliderDown(False)
        self.player.seek.assert_called_once_with(65_000)
        self.player.seek.reset_mock()
        QTest.keyClick(slider, Qt.Key.Key_Right)
        self.player.seek.assert_called_once_with(slider.value())
        self.assertEqual(self.player.position_ms, slider.value())

    def test_destroy_and_close_remove_listener(self):
        listener = self.bar._listener
        self.window.close()
        self.assertNotIn(listener, self.playback._listeners)
        self.playback.set_volume(33)
        self.assertEqual(self.bar.volume.value(), 80)
        standalone = TransportBar()
        standalone.bind(self.playback)
        listener = standalone._listener
        dispose(standalone)
        self.assertNotIn(listener, self.playback._listeners)
        self.playback.cycle_repeat()

    def test_async_cover_stale_failure_and_shutdown(self):
        entered, release, completed = threading.Event(), threading.Event(), threading.Event()
        data = cover_bytes()

        def read(track):
            if track.title == 'Título 0':
                entered.set()
                release.wait(5)
                completed.set()
                return data
            if track.title == 'Título 1':
                raise OSError('ilegível')
            return data

        bar = TransportBar()
        self.addCleanup(lambda: dispose(bar) if bar is not None else None)
        self.addCleanup(release.set)
        default = QPixmap(48, 48)
        default.fill(Qt.GlobalColor.blue)
        bar.bind(self.playback, read, default)
        self.play_from_songs()
        self.assertTrue(entered.wait(1))
        self.playback.next()
        release.set()
        self.assertTrue(wait_until(completed.is_set))
        pause(50)
        self.assertEqual(bar.cover.pixmap().toImage().pixelColor(0, 0), Qt.GlobalColor.blue)
        self.playback.next()
        self.assertTrue(wait_until(lambda: bar.cover.pixmap().toImage().pixelColor(0, 0) == Qt.GlobalColor.red))
        self.playback.clear()
        self.assertEqual(bar.cover.pixmap().toImage().pixelColor(0, 0), Qt.GlobalColor.blue)
        # Uma leitura pendente pode terminar depois que o widget foi destruído.
        release.clear()
        entered.clear()
        self.play_from_songs()
        self.assertTrue(entered.wait(1))
        dispose(bar)
        bar = None
        release.set()
        pause(30)

    def test_binding_initializes_current_position_and_player_duration(self):
        self.play_from_songs()
        self.player.advance(42_000)
        bar = TransportBar()
        self.addCleanup(dispose, bar)
        bar.bind(self.playback)
        self.assertEqual(bar.position.value(), 42_000)
        self.assertEqual(bar.time_label.text(), '0:42 / 3:00')
        self.player.durations[self.player.path] = 95_000
        self.playback.on_duration(95_000)
        self.assertEqual(bar.position.maximum(), 95_000)
        self.assertEqual(bar.time_label.text(), '0:42 / 1:35')


if __name__ == '__main__':
    unittest.main()
