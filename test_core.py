"""Testes sem rede. Execute com: python -m unittest"""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import core

MP3 = core.AUDIO_FORMATS[0]


class FakeYoutubeDL:
    """Imita o yt-dlp: "baixa" gerando um arquivo na pasta temporária."""

    infos: list = []  # Respostas sucessivas de extract_info.
    on_download = None

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def extract_info(self, url, download, process):
        return self.infos.pop(0)

    def process_ie_result(self, info, download):
        if self.on_download:
            self.on_download()
        (Path(self.options["paths"]["home"]) / "video.mp3").write_bytes(b"audio")


def run_extraction(dest, *, infos=None, on_download=None, cancel=None, metadata=core.AudioMetadata()):
    fake = type("Fake", (FakeYoutubeDL,), {"infos": infos or [{"title": "video"}], "on_download": on_download})
    with mock.patch.object(core.yt_dlp, "YoutubeDL", fake), mock.patch.object(core, "find_ffmpeg", lambda: "ffmpeg"):
        return core.extract_audio(
            "https://youtu.be/x", dest, MP3, lambda _: None, cancel or threading.Event(), metadata
        )


class UrlTests(unittest.TestCase):
    def test_accepts_youtube_urls(self):
        for url in (
            "https://www.youtube.com/watch?v=abc",
            "http://youtube.com/watch?v=abc",
            "https://m.youtube.com/watch?v=abc",
            "https://music.youtube.com/watch?v=abc",
            "  https://youtu.be/abc  ",
        ):
            self.assertTrue(core.is_youtube_url(url), url)

    def test_rejects_other_urls(self):
        for url in (
            "",
            "youtube.com/watch?v=abc",
            "ftp://youtube.com/watch?v=abc",
            "https://example.com/?u=youtube.com",
            "https://youtube.com.evil.example/watch?v=abc",
            "http://[invalid",
        ):
            self.assertFalse(core.is_youtube_url(url), url)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dest = Path(temp.name)
        # O áudio falso não é um arquivo válido; os gravadores reais estão em test_tags.py.
        patcher = mock.patch.object(core.tags, "write_tags")
        self.write_tags = patcher.start()
        self.addCleanup(patcher.stop)

    def test_metadata_defaults_to_video_title_and_no_author(self):
        run_extraction(self.dest, infos=[{"title": "Título do vídeo"}])
        _, title, author, cover = self.write_tags.call_args.args
        self.assertEqual((title, author), ("Título do vídeo", ""))
        self.assertEqual(cover, core.tags.load_cover(None))

    def test_user_metadata_replaces_defaults(self):
        run_extraction(
            self.dest,
            infos=[{"title": "Título do vídeo"}],
            metadata=core.AudioMetadata(title="Meu nome", author="Eu"),
        )
        _, title, author, _ = self.write_tags.call_args.args
        self.assertEqual((title, author), ("Meu nome", "Eu"))

    def test_invalid_cover_fails_before_downloading(self):
        download = mock.Mock()
        with self.assertRaisesRegex(core.ExtractionError, "capa"):
            run_extraction(
                self.dest,
                on_download=download,
                metadata=core.AudioMetadata(cover=self.dest / "nao-existe.png"),
            )
        download.assert_not_called()

    def test_saves_file_in_destination(self):
        path = run_extraction(self.dest)
        self.assertEqual(path, self.dest / "video.mp3")
        self.assertEqual(path.read_bytes(), b"audio")

    def test_creates_missing_destination(self):
        path = run_extraction(self.dest / "nova" / "pasta")
        self.assertTrue(path.exists())

    def test_never_overwrites_existing_files(self):
        (self.dest / "video.mp3").write_bytes(b"antigo")
        (self.dest / "video (1).mp3").write_bytes(b"antigo")
        path = run_extraction(self.dest)
        self.assertEqual(path.name, "video (2).mp3")
        self.assertEqual((self.dest / "video.mp3").read_bytes(), b"antigo")

    def test_rejects_playlists(self):
        with self.assertRaisesRegex(core.ExtractionError, "playlist"):
            run_extraction(self.dest, infos=[{"_type": "playlist"}])

    def test_rejects_live_streams(self):
        with self.assertRaisesRegex(core.ExtractionError, "ao vivo"):
            run_extraction(self.dest, infos=[{"live_status": "is_live"}])

    def test_rejects_live_stream_behind_redirect(self):
        with self.assertRaisesRegex(core.ExtractionError, "ao vivo"):
            run_extraction(self.dest, infos=[{"_type": "url", "url": "real"}, {"live_status": "is_live"}])

    def test_follows_redirect_to_normal_video(self):
        path = run_extraction(self.dest, infos=[{"_type": "url", "url": "real"}, {"title": "video"}])
        self.assertTrue(path.exists())

    def test_cancel_during_conversion_saves_nothing(self):
        cancel = threading.Event()
        with self.assertRaises(core.ExtractionCancelled):
            run_extraction(self.dest, on_download=cancel.set, cancel=cancel)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_missing_ffmpeg_is_reported(self):
        with mock.patch.object(core, "find_ffmpeg", lambda: None):
            with self.assertRaisesRegex(core.ExtractionError, "ffmpeg"):
                core.extract_audio("https://youtu.be/x", self.dest, MP3, lambda _: None, threading.Event())


class UrlListTests(unittest.TestCase):
    def test_reads_one_url_per_line_ignoring_blanks_and_spaces(self):
        text = "  https://youtu.be/a  \n\n\thttps://www.youtube.com/watch?v=b\n   \n"
        self.assertEqual(
            core.parse_url_list(text), (["https://youtu.be/a", "https://www.youtube.com/watch?v=b"], [])
        )

    def test_repeated_urls_are_extracted_once(self):
        text = "https://youtu.be/a\nhttps://youtu.be/b\nhttps://youtu.be/a"
        self.assertEqual(core.parse_url_list(text), (["https://youtu.be/a", "https://youtu.be/b"], []))

    def test_reports_the_line_numbers_of_invalid_urls(self):
        text = "https://youtu.be/a\nisto não é url\n\nhttps://example.com/v"
        self.assertEqual(core.parse_url_list(text), (["https://youtu.be/a"], [2, 4]))

    def test_empty_text(self):
        self.assertEqual(core.parse_url_list("  \n \n"), ([], []))


class BatchTests(unittest.TestCase):
    """extract_batch com extract_audio simulado: só a lógica da fila é testada aqui."""

    def run_batch(self, outcomes, cancel=None, metadata=core.AudioMetadata()):
        """`outcomes` diz o que cada vídeo faz: um nome de arquivo, uma exceção ou uma função."""
        cancel = cancel or threading.Event()
        calls, progress, reported = [], [], []

        def fake_extract(url, dest, fmt, on_progress, cancel_event, meta):
            calls.append((url, meta))
            on_progress(core.Progress("Baixando...", 50))
            outcome = outcomes[url]
            if callable(outcome):
                outcome = outcome()
            if isinstance(outcome, BaseException):
                raise outcome
            return Path(outcome)

        with mock.patch.object(core, "extract_audio", fake_extract):
            results = core.extract_batch(
                list(outcomes),
                Path("destino"),
                MP3,
                metadata,
                on_progress=lambda i, p: progress.append((i, p.message)),
                on_result=lambda i, r: reported.append((i, r)),
                cancel=cancel,
            )
        return results, calls, progress, reported

    def test_extracts_every_url_in_order(self):
        results, calls, progress, reported = self.run_batch({"u1": "a.mp3", "u2": "b.mp3"})
        self.assertEqual([r.path for r in results], [Path("a.mp3"), Path("b.mp3")])
        self.assertEqual([url for url, _ in calls], ["u1", "u2"])
        self.assertEqual(progress, [(0, "Baixando..."), (1, "Baixando...")])
        self.assertEqual([i for i, _ in reported], [0, 1])

    def test_a_failure_does_not_stop_the_rest(self):
        results, _, _, _ = self.run_batch(
            {"u1": core.ExtractionError("indisponível"), "u2": RuntimeError("estranho"), "u3": "c.mp3"}
        )
        self.assertEqual(results[0].error, "indisponível")
        self.assertIn("estranho", results[1].error)
        self.assertEqual(results[2].path, Path("c.mp3"))

    def test_cancel_stops_current_and_marks_the_rest(self):
        cancel = threading.Event()

        def cancelled_while_downloading():
            cancel.set()
            return core.ExtractionCancelled()

        results, calls, _, reported = self.run_batch(
            {"u1": "a.mp3", "u2": cancelled_while_downloading, "u3": "c.mp3"}, cancel=cancel
        )
        self.assertEqual(results[0].path, Path("a.mp3"))
        self.assertTrue(results[1].cancelled and results[2].cancelled)
        self.assertEqual([url for url, _ in calls], ["u1", "u2"])  # u3 nem começou.
        self.assertEqual(len(reported), 3)

    def test_same_author_and_cover_go_to_every_video(self):
        metadata = core.AudioMetadata(author="Banda", cover=None)
        _, calls, _, _ = self.run_batch({"u1": "a.mp3", "u2": "b.mp3"}, metadata=metadata)
        self.assertEqual([meta for _, meta in calls], [metadata, metadata])

    def test_invalid_cover_fails_once_before_any_download(self):
        with self.assertRaisesRegex(core.ExtractionError, "capa"):
            self.run_batch({"u1": "a.mp3"}, metadata=core.AudioMetadata(cover=Path("nao-existe.png")))


if __name__ == "__main__":
    unittest.main()
