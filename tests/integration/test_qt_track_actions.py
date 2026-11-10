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


class TrackActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

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
