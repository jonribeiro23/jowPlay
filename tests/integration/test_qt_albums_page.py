import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tests.fakes import FakeAudioPlayer, FakeLibraryStorage, InMemoryTrackRepository
from tests.qt_support import dispose, pause, qt_app
from ytdown.application.playback import Playback
from ytdown.domain.library import Track
from ytdown.infrastructure.resources import asset
from ytdown.presentation.qt.albums_page import AlbumsPage


class Cache:
    def get_or_create(self, path):
        return None


class AlbumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        self.repo = InMemoryTrackRepository()
        self.storage = FakeLibraryStorage()
        self.playback = Playback(FakeAudioPlayer(), self.storage, tracks=self.repo)
        for i, number in enumerate((2, 1, None)):
            self.repo.add(Track(f'{i}.mp3', f'Faixa {i}', datetime(2026, 1, i + 1),
                                artist='João', album='Verão', year=2020,
                                track_no=number, duration_ms=60000))
        self.repo.add(Track('other.mp3', 'Outra', datetime(2025, 1, 1), artist='Ana', album='Verão', year=2010))
        self.page = AlbumsPage(self.repo, self.playback, self.storage, Cache(), asset('default_cover.jpg'))
        self.addCleanup(dispose, self.page)
        self.addCleanup(self.page.model.shutdown)
        self.page.resize(700, 500)
        self.page.show()
        pause(20)

    def test_search_details_play_and_refresh(self):
        self.page.set_search_text('verao joao')
        self.assertEqual(self.page.model.rowCount(), 1)
        index = self.page.model.index(0, 0)
        self.page.open_index(index)
        self.assertEqual([t.track_no for t in self.page.track_model.tracks], [1, 2, None])
        self.assertIn('3:00', self.page.details.text())
        self.page.play_button.click()
        self.assertEqual(self.playback.queue, self.page.track_model.tracks)
        self.page.show_grid()
        self.page.play_index(index)
        self.assertEqual(self.playback.queue[0].track_no, 1)
        self.repo.add(Track('new.mp3', 'Nova', datetime.now(), artist='João', album='Verão', track_no=3))
        self.page.refresh()
        self.assertEqual(len(self.page.model.groups[('Verão', 'João')]), 4)

    def test_sorts_and_default_cover(self):
        self.page.sort.setCurrentIndex(1)
        self.assertEqual(self.page.model.visible[0].artist, 'Ana')
        self.page.sort.setCurrentIndex(2)
        self.assertEqual(self.page.model.visible[0].year, 2010)
        self.page.sort.setCurrentIndex(3)
        self.assertEqual(self.page.model.visible[0].artist, 'João')
        icon = self.page.model.data(self.page.model.index(0, 0), Qt.ItemDataRole.DecorationRole)
        self.assertFalse(icon.isNull())

    def test_500_albums_render_scroll(self):
        for i in range(500):
            self.repo.add(Track(f'extra{i}.mp3', str(i), datetime(2024, 1, 1) + timedelta(days=i),
                                artist='Artista', album=f'Álbum {i:03d}'))
        started = time.perf_counter()
        self.page.refresh()
        self.page.sort.setCurrentIndex(3)
        for row in (0, 250, 499, 0):
            self.page.view.scrollTo(self.page.model.index(row, 0))
            pause(10)
        elapsed = time.perf_counter() - started
        print(f'\n502 álbuns: atualizar, ordenar e rolar = {elapsed:.3f}s', flush=True)
        self.assertLess(elapsed, 3)
        self.assertEqual(self.page.model.rowCount(), 502)
        self.assertGreater(self.page.view.verticalScrollBar().maximum(), 0)
