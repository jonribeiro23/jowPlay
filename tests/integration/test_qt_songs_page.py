"""Músicas: modelo, interação, preferências, montagem e escala em Qt offscreen."""
import tempfile
import time
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from tests.qt_support import qt_app, dispose, pause, wait_until
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from tests.fakes import (FakeAudioPlayer, FakeLibraryStorage, InMemoryTrackRepository,
                         FakeDownloader, FakeCovers, FakeTags, FakeReader)
from ytdown.application.extraction import ExtractAudio, ExtractBatch
from ytdown.application.library import RegisterExtractedTrack
from ytdown.application.playback import Playback
from ytdown.bootstrap import build_library, build_main_window
from ytdown.domain.library import Track, TrackQuery
from ytdown.infrastructure.json_settings import JsonSettings
from ytdown.presentation.qt.songs_page import SongsPage, COLUMNS
from ytdown.presentation.qt.pages import PageId
from ytdown.presentation.qt.main_window import MainWindow
from ytdown.presentation.qt.send_dialog import PhoneSharing


class SongsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = InMemoryTrackRepository()
        self.player = FakeAudioPlayer()
        self.playback = Playback(self.player, FakeLibraryStorage(), tracks=self.repo)
        self.settings = JsonSettings(self.root / 'settings.json')
        for i, title in enumerate(('Zulu', 'Água', 'Beta')):
            self.repo.add(Track(f'{i}.mp3', title, datetime(2026, 1, i + 1),
                                duration_ms=(10-i)*1000, year=2020+i, track_no=10-i,
                                play_count=i, missing=i == 0))
        self.page = SongsPage(self.repo, self.playback, self.settings)
        self.addCleanup(dispose, self.page)
        self.page.show()

    def test_columns_count_format_missing_and_all_sort_fields(self):
        model = self.page.model
        self.assertEqual(model.rowCount(), 3)
        self.assertEqual(model.columnCount(), 9)
        self.assertEqual(self.page.count.text(), '3 faixas')
        for col, (label, field) in enumerate(COLUMNS):
            self.assertEqual(model.headerData(col, Qt.Orientation.Horizontal), label)
            for order in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):
                self.page.table.sortByColumn(col, order)
                self.assertEqual(model.tracks, self.repo.list_tracks(TrackQuery(sort=field, descending=order == Qt.SortOrder.DescendingOrder)))
        row = next(i for i,t in enumerate(model.tracks) if t.missing)
        self.assertIsNotNone(model.data(model.index(row,0), Qt.ItemDataRole.ForegroundRole))
        self.assertEqual(model.data(model.index(row,3)), '0:10')

    def test_enter_and_double_click_use_whole_visible_order(self):
        table = self.page.table
        table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        table.setCurrentIndex(self.page.model.index(1,0))
        QTest.keyClick(table, Qt.Key.Key_Return)
        self.assertEqual(self.playback.queue, self.page.model.tracks)
        self.assertEqual(self.playback.current_index, 1)
        table.scrollTo(self.page.model.index(2,0))
        pause(20)
        point = table.visualRect(self.page.model.index(2,0)).center()
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseDClick(table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(self.playback.current_index, 2)

    def test_selection_survives_sort_and_refresh_with_inclusion(self):
        table = self.page.table
        table.selectRow(0)
        table.selectionModel().select(self.page.model.index(1,0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        selected = {self.page.model.tracks[i.row()].id for i in table.selectionModel().selectedRows()}
        current_id = self.page.model.tracks[table.currentIndex().row()].id
        table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        self.repo.add(Track('new.mp3', 'Nova', datetime.now()))
        self.page.refresh()
        self.assertEqual(self.page.count.text(), '4 faixas')
        self.assertEqual({self.page.model.tracks[i.row()].id for i in table.selectionModel().selectedRows()}, selected)
        self.assertEqual(self.page.model.tracks[table.currentIndex().row()].id, current_id)

    def test_preferences_roundtrip_shared_settings(self):
        self.settings.set('library_folder', 'C:/Nova')
        self.page.set_column_visible(2, False)
        self.page.table.horizontalHeader().moveSection(0, 3)
        self.page.table.sortByColumn(5, Qt.SortOrder.DescendingOrder)
        restored = SongsPage(self.repo, self.playback, JsonSettings(self.root / 'settings.json'))
        self.addCleanup(dispose, restored)
        self.assertTrue(restored.table.isColumnHidden(2))
        self.assertEqual(restored.table.horizontalHeader().visualIndex(0), 3)
        self.assertEqual(restored.model.query, self.page.model.query)
        self.assertEqual(JsonSettings(self.root / 'settings.json').get('library_folder'), 'C:/Nova')

    def test_search_debounce_shortcuts_sort_selection_and_queue(self):
        self.repo.add(Track('accent.mp3', 'Canção', datetime.now(), artist='João', album='Verão', genre='Baião'))
        window = MainWindow(lambda page: self.page if page == PageId.SONGS else QWidget())
        self.addCleanup(dispose, window)
        self.addCleanup(self.page.setParent, None)
        window.show()
        window.activateWindow()
        pause(20)
        self.page.refresh()
        self.page.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        self.page.table.selectRow(0)
        selected = self.page.model.tracks[0].id
        self.playback.play_tracks(self.page.model.tracks)
        queue = list(self.playback.queue)
        QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(window.search.hasFocus())
        QTest.keyClicks(window.search, 'CANCAO joao verao baiao')
        self.assertEqual(self.page.model.rowCount(), 4)
        pause(300)
        self.assertEqual([t.title for t in self.page.model.tracks], ['Canção'])
        self.assertEqual(self.playback.queue, queue)
        self.page.table.sortByColumn(1, Qt.SortOrder.DescendingOrder)
        self.assertEqual(self.page.model.query.text, 'CANCAO joao verao baiao')
        window.show_page(PageId.ARTISTS)
        self.assertFalse(window.search.isEnabled())
        window.show_page(PageId.SONGS)
        QTest.keyClick(window.search, Qt.Key.Key_Escape)
        self.assertEqual(self.page.model.rowCount(), 4)
        self.assertEqual(self.page.model.query.text, '')
        self.assertEqual(self.page.model.query.sort, COLUMNS[1][1])
        self.assertEqual({self.page.model.tracks[i.row()].id for i in self.page.table.selectionModel().selectedRows()}, {selected})
        self.assertEqual(self.playback.queue, queue)

    def test_replaced_track_in_queue_loads_fresh_path(self):
        tracks = self.repo.list_tracks()
        self.playback.play_tracks(tracks)
        new = replace(tracks[1], rel_path='replacement.mp3')
        self.repo.update(new)
        self.playback.next()
        self.assertEqual(self.player.path.name, 'replacement.mp3')
        self.assertEqual(self.playback.current, new)

    def test_remove_unavailable_removes_it_from_list_and_queue(self):
        missing = next(track for track in self.page.model.tracks if track.missing)
        self.playback.play_tracks(self.page.model.tracks)

        def remove():
            self.repo.remove(missing.id)
            return {missing.id}

        self.page._remove_unavailable = remove
        self.page._update_count()
        self.page.remove_unavailable_button.click()
        self.assertNotIn(missing, self.page.model.tracks)
        self.assertNotIn(missing, self.playback.queue)

    def test_bootstrap_extraction_refresh_shutdown_and_5000_rows(self):
        library = build_library(self.root/'db.sqlite', self.root/'prefs.json', self.root/'music')
        self.addCleanup(library.close)
        from ytdown.infrastructure.qt_audio_player import QtAudioPlayer
        player = QtAudioPlayer(self.app)
        self.addCleanup(player.shutdown)
        playback = Playback(player, library.storage, tracks=library.tracks)
        sharing = PhoneSharing(lambda callback: None)
        library.register = RegisterExtractedTrack(library.storage, library.tracks, FakeReader())
        covers = FakeCovers()
        batch = ExtractBatch(ExtractAudio(FakeDownloader(), covers, FakeTags()), covers)
        window = build_main_window(library, playback, batch, sharing)
        window.closing.connect(player.shutdown)
        self.addCleanup(dispose, window)
        page = window.page(PageId.SONGS)
        self.assertIs(page.settings, library.settings)
        for i in range(5000):
            library.tracks.add(Track(f'{i}.mp3', f'Título {i:05d}', datetime.now()))
        started = time.perf_counter()
        page.refresh()
        page.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        window.show()
        pause(30)
        for row in (0, 2500, 4999, 0):
            page.table.scrollTo(page.model.index(row, 0))
            pause(10)
            self.assertTrue(page.table.visualRect(page.model.index(row, 0)).intersects(page.table.viewport().rect()))
        elapsed = time.perf_counter() - started
        print(f"\n5000 tracks: refresh, sort, render and scroll = {elapsed:.3f}s", flush=True)
        self.assertLess(elapsed, 3)
        self.assertEqual(page.model.rowCount(), 5000)
        self.assertLess(page.height(), window.height())
        self.assertGreater(page.table.verticalScrollBar().maximum(), 0)
        self.assertEqual(window.pages.currentWidget().verticalScrollBar().maximum(), 0)
        extract = window.page(PageId.EXTRACT)
        extract.urls.setPlainText('https://youtu.be/video1')
        extract.start()
        self.assertTrue(wait_until(lambda: not extract.is_working()))
        self.assertEqual(page.model.rowCount(), 5001)
        for kind, expected in ((PageId.SONGS, len(library.tracks.list_tracks())),
                               (PageId.ARTISTS, len(library.tracks.artists())),
                               (PageId.ALBUMS, len(library.tracks.albums())),
                               (PageId.GENRES, len(library.tracks.genres()))):
            self.assertEqual(window.navigation._items[kind].text(1), str(expected))
        self.assertEqual(len(extract.saved_files), 1)
        self.assertTrue(extract.saved_files[0].is_file())
        # Carrega um arquivo real sem precisar tocar som, e fecha pela janela.
        import wave
        audio = library.storage.absolute('test.wav')
        audio.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(audio), 'wb') as stream:
            stream.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            stream.writeframes(b'\0\0' * 800)
        player.load(audio)
        self.assertIsNotNone(player.source)
        window.close()
        self.assertIsNone(player.source)
