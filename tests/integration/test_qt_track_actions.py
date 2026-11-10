"""Ações de faixas nas quatro tabelas, inclusive resultados filtrados."""
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QItemSelectionModel, Qt

from tests.fakes import FakeAudioPlayer, FakeLibraryStorage, InMemoryTrackRepository
from tests.qt_support import dispose, qt_app
from ytdown.application.playback import Playback
from ytdown.domain.library import Track
from ytdown.infrastructure.json_settings import JsonSettings
from ytdown.presentation.qt.albums_page import AlbumsPage
from ytdown.presentation.qt.groups_page import GroupsPage
from ytdown.presentation.qt.songs_page import SongsPage
from ytdown.presentation.qt.send_dialog import PhoneSharing
from ytdown.application.sharing import SharingSession
from ytdown.infrastructure.sharing.server import LocalShareServer
from tests.fakes import FakeDevices


class TrackActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_selected_tracks_reach_shared_dialog_from_all_lists(self):
        from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
        with tempfile.TemporaryDirectory() as temp:
            storage = FileSystemLibraryStorage(Path(temp))
            repo = InMemoryTrackRepository()
            for i in range(3):
                repo.add(Track(f'{i}.mp3', f'Faixa {i}', datetime.now(), artist='Artista', album='Álbum', genre='Gênero', missing=i == 2))
            storage.absolute('0.mp3').write_bytes(b'audio')
            storage.absolute('2.mp3').write_bytes(b'audio')
            sharing = PhoneSharing(lambda changed: LocalShareServer(SharingSession(FakeDevices(), changed), http_port=0, discovery_port=0))
            playback = Playback(FakeAudioPlayer(), storage)
            pages = [SongsPage(repo, playback, JsonSettings(Path(temp) / 'settings.json'), storage=storage, send_to_phone=sharing.send),
                     AlbumsPage(repo, playback, storage, object(), '', send_to_phone=sharing.send),
                     GroupsPage(repo, playback, 'artist', storage, sharing.send),
                     GroupsPage(repo, playback, 'genre', storage, sharing.send)]
            try:
                for page in pages[1:]:
                    page.open_index(page.model.index(0, 0))
                for page in pages:
                    selection = page.table.selectionModel()
                    for row in range(3):
                        selection.select(page.table.model().index(row, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                    with patch('ytdown.presentation.qt.track_actions.QMessageBox.warning') as warning:
                        menu = page.track_actions.make_menu()
                        next(a for a in menu.actions() if a.text() == 'Enviar para o celular').trigger()
                        self.assertIn('Faixa 1', warning.call_args.args[2])
                        self.assertIn('Faixa 2', warning.call_args.args[2])
                    self.assertEqual([name for name, _ in sharing.dialog.rows()], ['0.mp3'])
                self.assertIsNotNone(sharing.dialog)
            finally:
                sharing.stop()
                pages[1].shutdown()
                for page in pages:
                    dispose(page)

    def test_album_button_sends_entire_album_and_warns_about_missing(self):
        from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
        with tempfile.TemporaryDirectory() as temp:
            storage = FileSystemLibraryStorage(Path(temp))
            repo = InMemoryTrackRepository()
            for i in range(4):
                repo.add(Track(f'{i}.mp3', f'Faixa {i}', datetime.now(), artist='Artista', album='Álbum',
                               track_no=i + 1, missing=i == 2))
            for i in (0, 1, 2):
                storage.absolute(f'{i}.mp3').write_bytes(b'audio')
            sharing = PhoneSharing(lambda changed: LocalShareServer(SharingSession(FakeDevices(), changed), http_port=0, discovery_port=0))
            page = AlbumsPage(repo, Playback(FakeAudioPlayer(), storage), storage, object(), '', sharing.send)
            try:
                page.open_index(page.model.index(0, 0))
                page.table.selectRow(0)
                with patch('ytdown.presentation.qt.track_actions.QMessageBox.warning') as warning:
                    page.send_button.click()
                warning.assert_called_once()
                self.assertIn('Faixa 2', warning.call_args.args[2])
                self.assertIn('Faixa 3', warning.call_args.args[2])
                self.assertEqual([name for name, _ in sharing.dialog.rows()], ['0.mp3', '1.mp3'])
            finally:
                sharing.stop()
                page.shutdown()
                dispose(page)

    def test_playlist_button_and_menu_send_whole_playlist(self):
        from ytdown.application.playlists import AutomaticPlaylists, ManagePlaylists
        from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
        from ytdown.infrastructure.sqlite_library import SqliteTrackRepository
        from ytdown.infrastructure.sqlite_playlists import SqlitePlaylistRepository
        from ytdown.presentation.qt.navigation import NavigationPane
        from ytdown.presentation.qt.pages import PageId
        from ytdown.presentation.qt.playlists_page import PlaylistsPage
        with tempfile.TemporaryDirectory() as temp:
            storage = FileSystemLibraryStorage(Path(temp))
            repo = SqliteTrackRepository(Path(temp) / 'library.db')
            tracks = [repo.add(Track(f'{i}.mp3', f'Faixa {i}', datetime.now(), play_count=i + 1)) for i in range(3)]
            for i in (0, 2):
                storage.absolute(f'{i}.mp3').write_bytes(b'audio')
            service = ManagePlaylists(SqlitePlaylistRepository(repo))
            playback = Playback(FakeAudioPlayer(), storage)
            sharing = PhoneSharing(lambda changed: LocalShareServer(SharingSession(FakeDevices(), changed), http_port=0, discovery_port=0))
            page = PlaylistsPage(service, playback, AutomaticPlaylists(repo), storage, sharing.send)
            nav = NavigationPane()
            nav.bind_playlists(service, page)
            try:
                with patch('ytdown.presentation.qt.navigation.QInputDialog.getText', return_value=('Lista', True)):
                    nav.create_playlist([tracks[2], tracks[1], tracks[0]])
                self.assertFalse(page.send_button.isHidden())
                with patch('ytdown.presentation.qt.track_actions.QMessageBox.warning') as warning:
                    page.send_button.click()
                self.assertIn('Faixa 1', warning.call_args.args[2])
                self.assertEqual([name for name, _ in sharing.dialog.rows()], ['2.mp3', '0.mp3'])

                sharing.stop()
                root = nav._items[PageId.PLAYLISTS]
                automatic = next(root.child(i) for i in range(root.childCount()) if root.child(i).text(0) == 'Mais tocadas')
                menu = nav.playlist_menu(automatic)
                with patch('ytdown.presentation.qt.track_actions.QMessageBox.warning'):
                    next(a for a in menu.actions() if a.text() == 'Enviar para o celular').trigger()
                self.assertEqual([name for name, _ in sharing.dialog.rows()], ['2.mp3', '0.mp3'])

                self.assertNotIn('Enviar para o celular', [a.text() for a in nav.playlist_menu(root).actions()])
                without_phone = PlaylistsPage(service, playback)
                self.assertTrue(without_phone.send_button.isHidden())
                without_phone.detach_playback()
                dispose(without_phone)
            finally:
                sharing.stop()
                page.detach_playback()
                dispose(nav)
                dispose(page)
                repo.close()

    def test_queue_actions_in_every_track_list(self):
        repo = InMemoryTrackRepository()
        for i in range(3):
            repo.add(Track(f'{i}.mp3', f'Faixa {i}', datetime.now(), artist='Artista', album='Álbum', genre='Gênero'))
        storage = FakeLibraryStorage()
        playback = Playback(FakeAudioPlayer(), storage)
        with tempfile.TemporaryDirectory() as temp:
            pages = [SongsPage(repo, playback, JsonSettings(Path(temp) / 'settings.json'), storage=storage),
                     AlbumsPage(repo, playback, storage, object(), ''),
                     GroupsPage(repo, playback, 'artist', storage), GroupsPage(repo, playback, 'genre', storage)]
            try:
                pages[0].set_search_text('faixa')
                for page in pages[1:]:
                    page.open_index(page.model.index(0, 0))
                for page in pages:
                    with self.subTest(page=type(page).__name__, kind=getattr(page, 'kind', '')):
                        model = page.table.model()
                        # Repeated IDs represent distinct rows and must not be deduplicated.
                        model.tracks[2] = replace(model.tracks[0], title='Repetida')
                        selection = page.table.selectionModel()
                        for row in (2, 0):
                            selection.select(model.index(row, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                        chosen = [model.tracks[0], model.tracks[2]]
                        playback.play_tracks([model.tracks[1]])
                        menu = page.track_actions.make_menu()
                        actions = {action.text(): action for action in menu.actions()}
                        actions['Tocar em seguida'].trigger()
                        self.assertEqual(playback.queue, [model.tracks[1], *chosen])
                        actions['Adicionar à fila'].trigger()
                        self.assertEqual(playback.queue, [model.tracks[1], *chosen, *chosen])
                        actions['Tocar'].trigger()
                        self.assertEqual(playback.queue, chosen)
                        self.assertNotIn('Excluir', actions)
                        self.assertNotIn('Propriedades', actions)
                        menu.deleteLater()
            finally:
                pages[1].shutdown()
                for page in pages:
                    dispose(page)

    def test_explorer_only_for_existing_single_file(self):
        repo = InMemoryTrackRepository()
        with tempfile.TemporaryDirectory() as temp:
            from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
            storage = FileSystemLibraryStorage(Path(temp))
            path = storage.absolute('file.mp3')
            path.write_bytes(b'audio')
            repo.add(Track('file.mp3', 'Faixa', datetime.now()))
            page = SongsPage(repo, Playback(FakeAudioPlayer(), storage), JsonSettings(Path(temp) / 'settings.json'), storage=storage)
            try:
                page.table.selectRow(0)
                with patch('ytdown.presentation.qt.track_actions.sys.platform', 'win32'), patch('ytdown.presentation.qt.track_actions.subprocess.Popen') as launch:
                    menu = page.track_actions.make_menu()
                    next(action for action in menu.actions() if action.text() == 'Mostrar no Explorer').trigger()
                    launch.assert_called_once_with(['explorer.exe', '/select,', str(path)])
                    path.unlink()
                    self.assertNotIn('Mostrar no Explorer', [action.text() for action in page.track_actions.make_menu().actions()])
            finally:
                dispose(page)
