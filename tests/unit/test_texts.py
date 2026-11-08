import unittest
from pathlib import Path

from ytdown.domain.models import AUDIO_FORMATS, BatchResult, Progress, Stage
from ytdown.presentation import texts
from ytdown.presentation.texts import Tone

MP3 = AUDIO_FORMATS[0]
SAVED = BatchResult("u1", path=Path("C:/Musica/a.mp3"))
FAILED = BatchResult("u2", error="indisponível")
CANCELLED = BatchResult("u3", cancelled=True)


class ProgressTextTests(unittest.TestCase):
    def test_each_stage_has_a_text(self):
        for stage in Stage:
            self.assertTrue(texts.progress_text(Progress(stage), MP3))

    def test_download_shows_the_percentage_when_known(self):
        self.assertEqual(texts.progress_text(Progress(Stage.DOWNLOADING, 42.4), MP3), "Baixando... 42%")
        self.assertEqual(texts.progress_text(Progress(Stage.DOWNLOADING), MP3), "Baixando...")

    def test_conversion_names_the_chosen_format(self):
        self.assertEqual(texts.progress_text(Progress(Stage.CONVERTING), AUDIO_FORMATS[4]), "Convertendo para FLAC...")

    def test_queue_progress_counts_the_whole_queue(self):
        progress = texts.queue_progress(1, 4, Progress(Stage.DOWNLOADING, 50))
        self.assertEqual(progress.percent, 37.5)
        text = texts.queue_progress_text(1, 4, Progress(Stage.SAVING), MP3)
        self.assertEqual(text, "Vídeo 2 de 4: Salvando...")


class UrlProblemTests(unittest.TestCase):
    def test_valid_list_has_no_problem(self):
        self.assertIsNone(texts.url_problem(["u"], []))

    def test_names_the_invalid_lines(self):
        self.assertIn("linha 2", texts.url_problem(["u"], [2]).text)
        self.assertIn("linhas 2, 5", texts.url_problem(["u"], [2, 5]).text)

    def test_empty_list(self):
        self.assertEqual(texts.url_problem([], []).tone, Tone.ERROR)


class ResultSummaryTests(unittest.TestCase):
    def test_single_video(self):
        self.assertEqual(texts.result_summary([SAVED], "C:/Musica").tone, Tone.SUCCESS)
        self.assertIn("a.mp3", texts.result_summary([SAVED], "C:/Musica").text)
        self.assertEqual(texts.result_summary([CANCELLED], "C:/Musica").text, "Extração cancelada.")
        failed = texts.result_summary([FAILED], "C:/Musica")
        self.assertEqual((failed.tone, failed.text.splitlines()[-1]), (Tone.ERROR, "indisponível"))

    def test_all_saved(self):
        summary = texts.result_summary([SAVED, SAVED], "C:/Musica")
        self.assertEqual(summary.tone, Tone.SUCCESS)
        self.assertTrue(summary.text.startswith("Pronto! 2 de 2 áudios salvos"))

    def test_failures_show_the_full_reason(self):
        summary = texts.result_summary([SAVED, FAILED], "C:/Musica")
        self.assertEqual(summary.tone, Tone.ERROR)
        self.assertIn("1 vídeo falhou", summary.text)
        self.assertIn("• u2\n   indisponível", summary.text)

    def test_many_failures_are_shortened(self):
        summary = texts.result_summary([FAILED] * 5, "C:/Musica")
        self.assertEqual(summary.text.count("indisponível"), texts.MAX_FAILURES_SHOWN)
        self.assertIn("e mais 2", summary.text)

    def test_cancelled_queue(self):
        summary = texts.result_summary([SAVED, CANCELLED, CANCELLED], "C:/Musica")
        self.assertEqual(summary.tone, Tone.NEUTRAL)
        self.assertIn("2 vídeos não foram extraídos", summary.text)

    def test_processed_percent(self):
        self.assertEqual(texts.processed_percent([SAVED]), 100)
        self.assertEqual(texts.processed_percent([FAILED]), 0)
        self.assertEqual(texts.processed_percent([SAVED, FAILED, CANCELLED, CANCELLED]), 50)


class SharingTextTests(unittest.TestCase):
    def test_pairing_code_is_split_for_reading(self):
        self.assertEqual(texts.pairing_code("080677"), "080 677")

    def test_every_transfer_status_has_a_text(self):
        from ytdown.domain.sharing import TransferStatus

        self.assertEqual(set(texts.TRANSFER_STATUS), set(TransferStatus))


if __name__ == "__main__":
    unittest.main()
