"""YtDlpDownloader com o yt-dlp simulado: testa as regras do adaptador sem acessar o YouTube."""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from yt_dlp.utils import DownloadError

from ytdown.domain.errors import ExtractionError
from ytdown.domain.models import AUDIO_FORMATS, Stage
from ytdown.infrastructure import youtube
from ytdown.infrastructure.youtube import YtDlpDownloader

MP3 = AUDIO_FORMATS[0]


def fake_youtube_dl(infos: list[dict], writes: str | None = "video.mp3", error: Exception | None = None):
    """Classe que imita yt_dlp.YoutubeDL: `infos` são as respostas sucessivas de extract_info."""
    infos = list(infos)

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def extract_info(self, url, download, process):
            return infos.pop(0)

        def process_ie_result(self, info, download):
            if error:
                raise error
            if writes:
                (Path(self.options["paths"]["home"]) / writes).write_bytes(b"audio")

    return FakeYoutubeDL


class YtDlpDownloaderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.stages = []

    def download(self, infos, **fake_options):
        with mock.patch.object(youtube.yt_dlp, "YoutubeDL", fake_youtube_dl(infos, **fake_options)):
            downloader = YtDlpDownloader(locate_ffmpeg=lambda: "ffmpeg")
            return downloader.download(
                "https://youtu.be/x", self.work, MP3, lambda p: self.stages.append(p.stage), threading.Event()
            )

    def test_returns_the_converted_file_and_the_video_title(self):
        audio = self.download([{"title": "Me at the zoo"}])
        self.assertEqual((audio.path, audio.title), (self.work / "video.mp3", "Me at the zoo"))
        self.assertEqual(self.stages, [Stage.FETCHING_INFO])

    def test_rejects_playlists_and_channels(self):
        for kind in ("playlist", "multi_video"):
            with self.subTest(kind), self.assertRaisesRegex(ExtractionError, "playlist"):
                self.download([{"_type": kind}])

    def test_rejects_live_streams(self):
        with self.assertRaisesRegex(ExtractionError, "ao vivo"):
            self.download([{"live_status": "is_live"}])

    def test_rejects_live_stream_behind_redirect(self):
        with self.assertRaisesRegex(ExtractionError, "ao vivo"):
            self.download([{"_type": "url", "url": "real"}, {"live_status": "is_live"}])

    def test_follows_redirect_to_normal_video(self):
        audio = self.download([{"_type": "url", "url": "real"}, {"title": "video"}])
        self.assertTrue(audio.path.exists())

    def test_yt_dlp_errors_become_readable_messages(self):
        with self.assertRaises(ExtractionError) as caught:
            self.download([{"title": "x"}], error=DownloadError("ERROR: [youtube] x: Video unavailable"))
        self.assertEqual(str(caught.exception), "[youtube] x: Video unavailable")

    def test_missing_output_is_reported(self):
        with self.assertRaisesRegex(ExtractionError, "não foi gerado"):
            self.download([{"title": "x"}], writes=None)

    def test_missing_ffmpeg_is_reported(self):
        downloader = YtDlpDownloader(locate_ffmpeg=lambda: None)
        with self.assertRaisesRegex(ExtractionError, "ffmpeg"):
            downloader.download("https://youtu.be/x", self.work, MP3, lambda _: None, threading.Event())

    def test_only_one_video_is_ever_requested(self):
        options = YtDlpDownloader._options(self.work, MP3, "ffmpeg", lambda _: None, threading.Event())
        self.assertTrue(options["noplaylist"])
        self.assertEqual(options["postprocessors"][0]["preferredquality"], "192")


if __name__ == "__main__":
    unittest.main()
