"""Página "Extrair" em Qt, com um ExtractBatch falso (sem rede), em modo offscreen."""

import threading
import unittest
from datetime import datetime
from pathlib import Path

from tests.qt_support import dispose, pause, qt_app, wait_until
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tests.fakes import FakeLibrary
from ytdown.domain.errors import InvalidCover
from ytdown.domain.library import DuplicatePolicy, Track
from ytdown.domain.models import AUDIO_FORMATS, AudioMetadata, BatchResult, Progress, Stage
from ytdown.presentation import texts
from ytdown.presentation.qt.extract_page import CANCEL_LABEL, EXTRACT_LABEL, ExtractPage, ask_duplicates_dialog
from ytdown.presentation.qt.main_window import MINIMUM_SIZE, MainWindow
from ytdown.presentation.qt.pages import PageId, PlaceholderPage

DEST = Path("C:/Musica")
URL_1, URL_2, URL_3 = (f"https://youtu.be/video{i}" for i in (1, 2, 3))


class FakeBatch:
    """Imita o ExtractBatch: cada URL pode dar certo, falhar ou ficar esperando o cancelamento."""

    def __init__(self, fail=(), block=(), error_before_start=None):
        self.fail, self.block, self.error_before_start = set(fail), set(block), error_before_start
        self.calls = []
        self.numbering = []
        self.blocked = threading.Event()

    def __call__(self, urls, destination, audio_format, metadata, on_progress, on_result, cancel,
                 number_tracks=False):
        self.calls.append((urls, destination, audio_format, metadata))
        self.numbering.append(number_tracks)
        if self.error_before_start:
            raise self.error_before_start
        results = []
        for index, url in enumerate(urls):
            if cancel.is_set():
                result = BatchResult(url, cancelled=True)
            else:
                on_progress(index, Progress(Stage.DOWNLOADING, 50))
                if url in self.block:
                    self.blocked.set()
                    cancel.wait(5)
                    result = BatchResult(url, cancelled=True)
                elif url in self.fail:
                    result = BatchResult(url, error="[youtube] video: This video is unavailable")
                else:
                    result = BatchResult(url, path=destination.folder / f"video {index + 1}.mp3")
            results.append(result)
            on_result(index, result)
        return results


class ExtractPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def make_page(self, batch=None, send_to_phone=None, library=None, ask=None, genres=None):
        self.batch = batch or FakeBatch()
        self.library = library or FakeLibrary()
        self.asked = []
        self.genres = genres if genres is not None else []

        def record_and_answer(duplicates):
            self.asked.append(duplicates)
            return ask(duplicates) if ask else DuplicatePolicy.KEEP_BOTH

        page = ExtractPage(self.batch, self.library, send_to_phone=send_to_phone, ask_duplicates=record_and_answer,
                           genre_suggestions=lambda: list(self.genres))
        page.show()
        self.addCleanup(dispose, page)  # As limpezas rodam em ordem inversa: primeiro para a extração.
        self.addCleanup(self.stop_extraction, page)
        return page

    @staticmethod
    def stop_extraction(page):
        """Mesmo se o teste falhar, nenhuma thread fica rodando: o Qt aborta o processo nesse caso."""
        page.cancel()
        wait_until(lambda: not page.is_working(), 5000)

    def run_extraction(self, page, *urls, start=None):
        page.urls.setPlainText("\n".join(urls))
        (start or page.main_button.click)()
        self.assertTrue(wait_until(lambda: not page.is_working(), 5000), "a extração não terminou")

    # --- validação

    def test_invalid_lines_are_reported_without_starting(self):
        page = self.make_page()
        page.urls.setPlainText(f"{URL_1}\nisto não é url\nhttps://example.com/v")
        page.main_button.click()
        self.assertEqual(page.status.text(), texts.url_problem([URL_1], [2, 3]).text)
        self.assertEqual(self.batch.calls, [])

    def test_empty_box(self):
        page = self.make_page()
        page.main_button.click()
        self.assertEqual(page.status.text(), "Cole a URL de pelo menos um vídeo do YouTube.")

    # --- álbum, gênero, ano e nº da faixa (JOW-20)

    def fill_details(self, page, album="Disco", genre="Rock", year="2024", track=""):
        page.album_field.setText(album)
        page.genre_field.setText(genre)
        page.year_field.setText(year)
        page.track_field.setText(track)

    def test_album_genre_year_and_number_go_to_the_audio(self):
        page = self.make_page()
        self.fill_details(page, track="3")
        self.run_extraction(page, URL_1)
        metadata = self.batch.calls[0][3]
        self.assertEqual((metadata.album, metadata.genre, metadata.year, metadata.track_no), ("Disco", "Rock", 2024, 3))
        self.assertEqual(self.batch.numbering, [False])

    def test_empty_fields_mean_no_value(self):
        page = self.make_page()
        self.run_extraction(page, URL_1)
        self.assertEqual(self.batch.calls[0][3], AudioMetadata())

    def test_invalid_year_is_explained_before_starting(self):
        for year in ("24", "abcd", "0999", "-200"):
            with self.subTest(year):
                page = self.make_page()
                self.fill_details(page, year=year)
                page.urls.setPlainText(URL_1)
                page.main_button.click()
                self.assertEqual(page.status.text(), texts.INVALID_YEAR.text)
                self.assertEqual(page.status.property("tone"), "error")
                self.assertEqual(self.batch.calls, [])

    def test_invalid_track_number_is_explained_before_starting(self):
        for track in ("0", "-1", "x", "1.5"):
            with self.subTest(track):
                page = self.make_page()
                self.fill_details(page, track=track)
                page.urls.setPlainText(URL_1)
                page.main_button.click()
                self.assertEqual(page.status.text(), texts.INVALID_TRACK_NO.text)
                self.assertEqual(self.batch.calls, [])

    def test_numbering_option_only_exists_for_a_queue(self):
        page = self.make_page()
        page.urls.setPlainText(URL_1)
        self.assertFalse(page.number_tracks_box.isVisible())
        self.assertTrue(page.track_field.isEnabled())
        page.urls.setPlainText(f"{URL_1}\n{URL_2}")
        self.assertTrue(page.number_tracks_box.isVisible() and page.number_tracks_box.isEnabled())
        self.assertFalse(page.track_field.isEnabled())  # Sem numerar, cada vídeo fica sem nº.
        self.assertEqual(page.track_label.text(), texts.TRACK_LABEL_BATCH)
        page.number_tracks_box.setChecked(True)
        self.assertTrue(page.track_field.isEnabled())  # Agora é o nº da primeira faixa.
        self.assertEqual(page.track_label.text(), texts.TRACK_LABEL_NUMBERED)

    def test_queue_as_an_album_numbered_in_the_order_of_the_list(self):
        page = self.make_page()
        self.fill_details(page)
        page.urls.setPlainText("\n".join((URL_1, URL_2, URL_3)))
        page.number_tracks_box.setChecked(True)
        self.run_extraction(page, URL_1, URL_2, URL_3)
        self.assertEqual(self.batch.numbering, [True])
        metadata = self.batch.calls[0][3]
        self.assertEqual((metadata.album, metadata.genre, metadata.year, metadata.track_no), ("Disco", "Rock", 2024, None))

    def test_queue_without_numbering_ignores_the_disabled_number_field(self):
        page = self.make_page()
        page.track_field.setText("abc")  # Digitado antes de virar fila; o campo fica desativado.
        self.run_extraction(page, URL_1, URL_2)
        self.assertEqual(len(self.batch.calls), 1)
        self.assertEqual((self.batch.numbering, self.batch.calls[0][3].track_no), ([False], None))

    def test_all_details_are_cleared_after_a_successful_extraction(self):
        page = self.make_page()
        self.fill_details(page)
        page.urls.setPlainText(f"{URL_1}\n{URL_2}")
        page.number_tracks_box.setChecked(True)
        page.track_field.setText("5")
        self.run_extraction(page, URL_1, URL_2)
        self.assertEqual([field.text() for field in (page.album_field, page.genre_field, page.year_field,
                                                     page.track_field)], ["", "", "", ""])
        self.assertFalse(page.number_tracks_box.isChecked())

    def test_genre_suggestions_come_from_the_library_and_follow_new_extractions(self):
        page = self.make_page(genres=["MPB", "Rock"])
        self.assertEqual(page.genre_completer.model().stringList(), ["MPB", "Rock"])
        self.genres.append("Samba")
        self.run_extraction(page, URL_1)
        self.assertEqual(page.genre_completer.model().stringList(), ["MPB", "Rock", "Samba"])
        page.genre_completer.setCompletionPrefix("sam")
        self.assertEqual(page.genre_completer.currentCompletion(), "Samba")

    # --- biblioteca

    def test_there_is_no_folder_to_choose_the_library_folder_is_shown(self):
        page = self.make_page()
        self.assertFalse(hasattr(page, "destination"))
        self.assertIn(str(DEST), page.library_info.text())
        self.library.folder = Path("D:/Nova")  # Mudou nas Opções.
        page.refresh_library_folder()
        self.assertIn(str(Path("D:/Nova")), page.library_info.text())

    def test_saved_files_follow_the_library_to_its_new_folder(self):
        sent = []
        page = self.make_page(send_to_phone=sent.append)
        self.run_extraction(page, URL_1, URL_2)
        self.library.folder = Path("D:/Nova")
        page.refresh_library_folder()
        self.assertEqual(page.saved_files, [Path("D:/Nova/video 1.mp3"), Path("D:/Nova/video 2.mp3")])
        page.send_button.click()
        self.assertEqual(sent, [page.saved_files])

    def test_without_duplicates_nothing_is_asked(self):
        page = self.make_page()
        self.run_extraction(page, URL_1, URL_2)
        self.assertEqual(self.asked, [])
        self.assertEqual(self.batch.calls[0][1].policy, DuplicatePolicy.KEEP_BOTH)
        self.assertIn(f"áudios salvos em:\n{DEST}", page.status.text())

    def test_duplicates_are_asked_once_before_extracting(self):
        old = Track(rel_path="a/b/c.mp3", title="Antiga", added_at=datetime(2025, 1, 1))
        library = FakeLibrary(duplicates={URL_1: old, URL_3: old})
        page = self.make_page(library=library, ask=lambda duplicates: DuplicatePolicy.REPLACE)
        self.run_extraction(page, URL_1, URL_2, URL_3)
        self.assertEqual(self.asked, [[(URL_1, old), (URL_3, old)]])
        self.assertEqual(self.batch.calls[0][1].policy, DuplicatePolicy.REPLACE)

    def test_cancelling_the_duplicate_question_extracts_nothing(self):
        old = Track(rel_path="a/b/c.mp3", title="Antiga", added_at=datetime(2025, 1, 1))
        page = self.make_page(library=FakeLibrary(duplicates={URL_1: old}), ask=lambda duplicates: None)
        page.urls.setPlainText(URL_1)
        page.main_button.click()
        self.assertEqual(self.batch.calls, [])
        self.assertFalse(page.is_working())
        self.assertEqual(page.status.text(), texts.NOTHING_EXTRACTED.text)

    # --- um vídeo

    def test_single_video_success(self):
        page = self.make_page()
        page.format_box.setCurrentIndex(4)  # FLAC
        page.title_field.setText("Meu nome")
        page.artist_field.setText("Eu")
        page.cover_field.setText('"C:/capa.png"')
        self.run_extraction(page, URL_1)

        urls, destination, audio_format, metadata = self.batch.calls[0]
        self.assertEqual((urls, destination.folder, audio_format), ([URL_1], DEST, AUDIO_FORMATS[4]))
        self.assertEqual((metadata.title, metadata.artist, metadata.cover), ("Meu nome", "Eu", Path("C:/capa.png")))
        self.assertTrue(page.status.text().startswith("Pronto! Áudio salvo em:"))
        self.assertFalse(page.queue.isVisible())
        self.assertTrue(page.show_file_button.isEnabled())
        self.assertEqual((page.title_field.text(), page.artist_field.text(), page.cover_field.text()), ("", "", ""))
        self.assertEqual(page.progress.value(), 100)

    def test_ctrl_enter_in_the_url_box_starts(self):
        page = self.make_page()
        page.urls.setFocus()
        self.run_extraction(page, URL_1, start=lambda: QTest.keyClick(
            page.urls, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier))
        self.assertEqual(len(self.batch.calls), 1)

    def test_invalid_cover_fails_before_the_queue(self):
        page = self.make_page(FakeBatch(error_before_start=InvalidCover("Não foi possível ler a imagem de capa: x.png")))
        self.run_extraction(page, URL_1, URL_2)
        self.assertEqual(page.status.text(),
                         "Não foi possível extrair o áudio.\nNão foi possível ler a imagem de capa: x.png")
        self.assertEqual(page.status.property("tone"), "error")  # A cor vem do tema (test_qt_theme).

    # --- fila

    def test_queue_with_a_failure_shows_each_status_and_the_full_reason(self):
        page = self.make_page(FakeBatch(fail={URL_2}))
        self.run_extraction(page, URL_1, URL_2, URL_3)
        self.assertTrue(page.queue.isVisible())
        rows = [(page.queue.topLevelItem(i).text(0), page.queue.topLevelItem(i).text(1)) for i in range(3)]
        self.assertEqual(rows, [("video 1.mp3", "Salvo"),
                                (URL_2, "Falhou: [youtube] video: This video is unavailable"),
                                ("video 3.mp3", "Salvo")])
        self.assertIn("2 de 3 áudios salvos", page.status.text())
        self.assertIn(f"• {URL_2}\n   [youtube] video: This video is unavailable", page.status.text())
        self.assertEqual(page.saved_files, [DEST / "video 1.mp3", DEST / "video 3.mp3"])

    def test_cancel_in_the_middle_of_the_queue(self):
        page = self.make_page(FakeBatch(block={URL_2}))
        page.urls.setPlainText("\n".join((URL_1, URL_2, URL_3)))
        page.main_button.click()
        self.assertTrue(wait_until(self.batch.blocked.is_set, 5000))
        self.assertEqual(page.main_button.text(), CANCEL_LABEL)
        page.main_button.click()
        self.assertEqual(page.status.text(), texts.CANCELLING)
        self.assertFalse(page.main_button.isEnabled())
        self.assertTrue(wait_until(lambda: not page.is_working(), 5000))

        statuses = [page.queue.topLevelItem(i).text(1) for i in range(3)]
        self.assertEqual(statuses, ["Salvo", "Cancelado", "Cancelado"])
        self.assertIn("Extração cancelada: 2 vídeos não foram extraídos.", page.status.text())
        self.assertEqual((page.main_button.text(), page.main_button.isEnabled()), (EXTRACT_LABEL, True))

    def test_title_field_is_disabled_for_several_videos_and_while_working(self):
        page = self.make_page(FakeBatch(block={URL_1}))
        page.urls.setPlainText(f"{URL_1}\n{URL_2}")
        self.assertFalse(page.title_field.isEnabled())
        self.assertEqual(page.title_label.text(), texts.TITLE_LABEL_BATCH)
        page.urls.setPlainText(URL_1)
        self.assertTrue(page.title_field.isEnabled())
        page.main_button.click()
        self.assertTrue(wait_until(self.batch.blocked.is_set, 5000))
        self.assertFalse(page.title_field.isEnabled())
        self.assertFalse(page.urls.isEnabled())
        page.cancel()
        self.assertTrue(wait_until(lambda: not page.is_working(), 5000))
        self.assertTrue(page.title_field.isEnabled())

    # --- envio para o celular

    def test_send_button_only_exists_with_a_destination_for_the_files(self):
        self.assertTrue(self.make_page().send_button.isHidden())
        sent = []
        page = self.make_page(send_to_phone=sent.append)
        self.assertFalse(page.send_button.isHidden())
        self.run_extraction(page, URL_1, URL_2)
        page.send_button.click()
        self.assertEqual(sent, [[DEST / "video 1.mp3", DEST / "video 2.mp3"]])


class ClosingDuringExtractionTests(unittest.TestCase):
    """Fechar a janela no meio da extração: ela some, a extração é cancelada e só então o app fecha."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_window_waits_for_the_extraction_to_finish(self):
        batch = FakeBatch(block={URL_1})
        accepted = []

        class RecordingWindow(MainWindow):
            def closeEvent(self, event):
                super().closeEvent(event)
                accepted.append(event.isAccepted())

        window = RecordingWindow(lambda p: ExtractPage(batch, FakeLibrary()) if p is PageId.EXTRACT
                                 else PlaceholderPage(p))
        window.show()
        page = window.page(PageId.EXTRACT)
        self.addCleanup(dispose, window)
        self.addCleanup(ExtractPageTests.stop_extraction, page)
        page.urls.setPlainText(URL_1)
        page.main_button.click()
        self.assertTrue(wait_until(batch.blocked.is_set, 5000))

        window.close()
        self.assertEqual(accepted, [False])  # Ainda trabalhando: só escondeu.
        self.assertFalse(window.isVisible())
        self.assertTrue(wait_until(lambda: accepted == [False, True], 5000))  # Fechou ao terminar.
        self.assertFalse(page.is_working())


class SmallWindowTests(unittest.TestCase):
    """Na janela pequena, a página rola; os campos nunca ficam espremidos."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_fields_keep_their_height_and_the_page_scrolls(self):
        window = MainWindow(lambda p: ExtractPage(FakeBatch(), FakeLibrary(folder=Path("C:/" + "pasta/" * 30)))
                            if p is PageId.EXTRACT else PlaceholderPage(p))
        self.addCleanup(dispose, window)
        window.resize(*MINIMUM_SIZE)
        window.show()
        window.show_page(PageId.EXTRACT)
        page = window.page(PageId.EXTRACT)
        page._show(texts.Message("Uma mensagem longa\n" * 6))
        pause(50)
        for field in (page.year_field, page.track_field, page.album_field, page.cover_field):
            with self.subTest(field.objectName() or type(field).__name__):
                self.assertGreaterEqual(field.height(), field.minimumSizeHint().height())
        scroll = window.pages.currentWidget()
        self.assertTrue(scroll.verticalScrollBar().maximum() > 0)


class DuplicateQuestionTests(unittest.TestCase):
    """A pergunta de verdade (QMessageBox), respondida por um clique."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def answer(self, button_text):
        def click():
            box = QApplication.activeModalWidget()
            self.seen.append(box.text())
            next(b for b in box.buttons() if b.text() == button_text).click()

        self.seen = []
        QTimer.singleShot(0, click)
        old = Track(rel_path="a/b/c.mp3", title="Me at the zoo", added_at=datetime(2025, 1, 1), artist="jawed")
        return ask_duplicates_dialog(None)([(URL_1, old)])

    def test_each_button_gives_its_choice(self):
        for label, expected in ((texts.REPLACE_LABEL, DuplicatePolicy.REPLACE),
                                (texts.KEEP_BOTH_LABEL, DuplicatePolicy.KEEP_BOTH),
                                (texts.CANCEL_LABEL, None)):
            with self.subTest(label):
                self.assertEqual(self.answer(label), expected)
                self.assertIn("Me at the zoo (jawed)", self.seen[0])


if __name__ == "__main__":
    unittest.main()
