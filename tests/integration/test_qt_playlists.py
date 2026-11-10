import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tests.fakes import FakeAudioPlayer, FakeLibraryStorage
from tests.integration.test_qt_play_queue_pane import Drop
from tests.qt_support import dispose, qt_app
from ytdown.application.playback import Playback
from ytdown.application.playlists import ManagePlaylists
from ytdown.domain.library import Track
from ytdown.infrastructure.json_settings import JsonSettings
from ytdown.infrastructure.sqlite_library import SqliteTrackRepository
from ytdown.infrastructure.sqlite_playlists import SqlitePlaylistRepository
from ytdown.presentation.qt.navigation import NavigationPane
from ytdown.presentation.qt.pages import PageId
from ytdown.presentation.qt.play_queue_pane import PlayQueuePane
from ytdown.presentation.qt.playlists_page import PlaylistsPage
from ytdown.presentation.qt.songs_page import SongsPage


class PlaylistUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_three_add_paths_reorder_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'library.db'
            repo = SqliteTrackRepository(path)
            a = repo.add(Track('a.mp3', 'A', datetime.now(), duration_ms=61000))
            b = repo.add(Track('b.mp3', 'B', datetime.now(), duration_ms=2000))
            service = ManagePlaylists(SqlitePlaylistRepository(repo))
            playback = Playback(FakeAudioPlayer(), FakeLibraryStorage())
            page = PlaylistsPage(service, playback)
            nav = NavigationPane()
            nav.bind_playlists(service, page)
            songs = SongsPage(repo, playback, JsonSettings(Path(directory) / 'settings.json'))
            songs.track_actions.playlist_navigation = nav
            queue = PlayQueuePane()
            queue.save_playlist = lambda tracks: nav.create_playlist(tracks)
            queue.bind(playback)
            nav.show()
            page.show()
            with patch('ytdown.presentation.qt.navigation.QInputDialog.getText', return_value=('Lista', True)):
                nav.create_playlist()
            playlist_id = page.playlist_id
            item = nav._items[PageId.PLAYLISTS].child(0)
            songs.table.selectRow(0)
            drop = Drop(songs.table, nav.visualItemRect(item).center(), tracks=True)
            nav.dropEvent(drop)
            self.assertTrue(drop.accepted)
            menu = songs.track_actions.make_menu()
            submenu = next(action.menu() for action in menu.actions() if action.text() == 'Adicionar à playlist')
            submenu.actions()[0].trigger()
            self.assertEqual([t.id for t in page.playlist.tracks], [a.id, a.id])
            playback.play_tracks([a, b, a])
            with patch('ytdown.presentation.qt.navigation.QInputDialog.getText', return_value=('Fila', True)):
                queue.save_button.click()
            saved_id = page.playlist_id
            self.assertEqual([t.id for t in page.playlist.tracks], [a.id, b.id, a.id])
            page.items.setCurrentRow(2)
            drop = Drop(page.items, page.items.visualItemRect(page.items.item(0)).topLeft())
            page.items.dropEvent(drop)
            self.assertTrue(drop.accepted)
            self.assertEqual([t.id for t in page.playlist.tracks], [a.id, a.id, b.id])
            self.assertEqual(page.total.text(), '3 faixas · 2:04')
            QTest.keyClick(page.items, Qt.Key.Key_Delete)
            self.assertEqual([t.id for t in page.playlist.tracks], [a.id, b.id])
            page.play(1)
            self.assertEqual(playback.current_index, 1)
            for widget in (queue, songs, nav, page):
                dispose(widget)
            repo.close()
            repo = SqliteTrackRepository(path)
            restored = SqlitePlaylistRepository(repo)
            self.assertEqual([t.id for t in restored.get(saved_id).tracks], [a.id, b.id])
            self.assertEqual([t.id for t in restored.get(playlist_id).tracks], [a.id, a.id])
            repo.close()
