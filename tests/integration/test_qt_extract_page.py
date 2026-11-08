"""Página "Extrair" em Qt, com um ExtractBatch falso (sem rede), em modo offscreen."""

import threading
import unittest
from pathlib import Path

from tests.qt_support import dispose, qt_app, wait_until
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from ytdown.domain.errors import InvalidCover
from ytdown.domain.models import AUDIO_FORMATS, BatchResult, Progress, Stage
from ytdown.presentation import texts
from ytdown.presentation.qt.extract_page import CANCEL_LABEL, EXTRACT_LABEL, ExtractPage
from ytdown.presentation.qt.main_window import MainWindow
from ytdown.presentation.qt.pages import PageId, PlaceholderPage

DEST = Path("C:/Musica")
URL_1, URL_2, URL_3 = (f"https://youtu.be/video{i}" for i in (1, 2, 3))


class FakeBatch:
    """Imita o ExtractBatch: cada URL pode dar certo, falhar ou ficar esperando o cancelamento."""

    def __init__(self, fail=(), block=(), error_before_start=None):
        self.fail, self.block, self.error_before_start = set(fail), set(block), error_before_start
        self.calls = []
        self.blocked = threading.Event()

    def __call__(self, urls, dest, audio_format, metadata, on_progress, on_result, cancel):
        self.calls.append((urls, dest, audio_format, metadata))
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
                    result = BatchResult(url, path=dest / f"video {index + 1}.mp3")
            results.append(result)
            on_result(index, result)
        return results


class ExtractPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def make_page(self, batch=None, send_to_phone=None):
        self.batch = batch or FakeBatch()
        page = ExtractPage(self.batch, send_to_phone=send_to_phone, default_destination=str(DEST))
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

    def test_destination_must_be_a_full_path(self):
        page = self.make_page()
        page.destination.setText("pasta relativa")
        page.urls.setPlainText(URL_1)
        page.main_button.click()
        self.assertEqual(page.status.text(), texts.INVALID_DESTINATION.text)
        self.assertEqual(self.batch.calls, [])

    # --- um vídeo

    def test_single_video_success(self):
        page = self.make_page()
        page.format_box.setCurrentIndex(4)  # FLAC
        page.title_field.setText("Meu nome")
        page.artist_field.setText("Eu")
        page.cover_field.setText('"C:/capa.png"')
        self.run_extraction(page, URL_1)

        urls, dest, audio_format, metadata = self.batch.calls[0]
        self.assertEqual((urls, dest, audio_format), ([URL_1], DEST, AUDIO_FORMATS[4]))
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

        window = RecordingWindow(lambda p: ExtractPage(batch) if p is PageId.EXTRACT else PlaceholderPage(p))
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


if __name__ == "__main__":
    unittest.main()
