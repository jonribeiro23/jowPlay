import unittest
from datetime import datetime

from tests.fakes import FakeAudioPlayer, FakeLibraryStorage, InMemoryTrackRepository
from tests.qt_support import dispose, qt_app
from ytdown.application.playback import Playback
from ytdown.domain.library import Track, UNKNOWN_ARTIST, UNKNOWN_GENRE
from ytdown.presentation.qt.groups_page import GroupsPage


class GroupsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        self.repo = InMemoryTrackRepository()
        self.playback = Playback(FakeAudioPlayer(), FakeLibraryStorage(), tracks=self.repo)
        for path, title, artist, album, genre in [
            ('1', 'Canção', 'João', 'Verão', 'Jazz'),
            ('2', 'Outra', 'João', 'Inverno', 'Rock'),
            ('3', 'Sem dados', '', '', ''),
            ('4', 'Mais uma', ' ', ' ', ' '),
        ]:
            self.repo.add(Track(path, title, datetime(2026, 1, 1), artist=artist, album=album, genre=genre))

    def page(self, kind):
        page = GroupsPage(self.repo, self.playback, kind)
        self.addCleanup(dispose, page)
        return page

    def test_artist_search_counts_detail_play_and_refresh(self):
        page = self.page('artist')
        for query in ('cancao', 'joao', 'verao', 'jazz', 'joao jazz'):
            page.set_search_text(query)
            self.assertEqual([a.name for a in page.model.visible], ['João'])
            self.assertEqual((page.model.visible[0].album_count, page.model.visible[0].track_count), (2, 2))
        page.open_index(page.model.index(0, 0))
        self.assertEqual(page.album_model.rowCount(), 2)
        self.assertEqual(page.track_model.rowCount(), 2)
        page.play_button.click()
        self.assertEqual(len(self.playback.queue), 2)
        self.repo.add(Track('5', 'Nova', datetime.now(), artist='João', album='Verão'))
        page.refresh()
        self.assertEqual(page.track_model.rowCount(), 3)
        page.show_list()
        page.set_search_text('')
        self.assertEqual(page.model.visible[-1].name, UNKNOWN_ARTIST)
        self.assertEqual(page.model.visible[-1].track_count, 2)
        self.assertEqual(page.model.visible[-1].album_count, 1)

    def test_genre_unknown_detail_and_play(self):
        page = self.page('genre')
        self.assertEqual(page.model.visible[-1].name, UNKNOWN_GENRE)
        self.assertEqual(page.model.visible[-1].track_count, 2)
        page.open_index(page.model.index(len(page.model.visible) - 1, 0))
        self.assertEqual(page.track_model.rowCount(), 2)
        page.play_button.click()
        self.assertEqual(len(self.playback.queue), 2)
