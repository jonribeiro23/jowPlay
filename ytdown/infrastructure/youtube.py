"""Download e conversão do áudio com yt-dlp e ffmpeg."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

from ytdown.application.ports import DownloadedAudio, ProgressCallback
from ytdown.domain.errors import ExtractionCancelled, ExtractionError
from ytdown.domain.models import AudioFormat, Progress, Stage
from ytdown.infrastructure.resources import find_ffmpeg

_REDIRECT_TYPES = ("url", "url_transparent")
_COLLECTION_TYPES = ("playlist", "multi_video")


class _SilentLogger:
    """Silencia o yt-dlp: um app com janela não tem console onde escrever."""

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


class YtDlpDownloader:
    """Implementa AudioDownloader."""

    def __init__(self, locate_ffmpeg: Callable[[], str | None] = find_ffmpeg) -> None:
        self._locate_ffmpeg = locate_ffmpeg

    def download(
        self,
        url: str,
        work_dir: Path,
        audio_format: AudioFormat,
        on_progress: ProgressCallback,
        cancel: threading.Event,
    ) -> DownloadedAudio:
        ffmpeg = self._locate_ffmpeg()
        if ffmpeg is None:
            raise ExtractionError("O ffmpeg não foi encontrado neste computador.")

        options = self._options(work_dir, audio_format, ffmpeg, on_progress, cancel)
        on_progress(Progress(Stage.FETCHING_INFO))
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = self._single_video_info(ydl, url)
                ydl.process_ie_result(info, download=True)
        except DownloadCancelled as exc:
            raise ExtractionCancelled() from exc
        except DownloadError as exc:
            raise ExtractionError(str(exc).removeprefix("ERROR: ")) from exc

        if cancel.is_set():
            raise ExtractionCancelled()
        produced = sorted(work_dir.glob(f"*.{audio_format.extension}"))
        if not produced:
            raise ExtractionError("A conversão terminou, mas o arquivo de áudio não foi gerado.")
        return DownloadedAudio(produced[0], info.get("title"), info.get("webpage_url") or url)

    @staticmethod
    def _single_video_info(ydl: yt_dlp.YoutubeDL, url: str) -> dict:
        """Lê os metadados e recusa o que não é um único vídeo gravado."""
        # process=False só lê os metadados, sem percorrer playlists inteiras.
        info = ydl.extract_info(url, download=False, process=False)
        # Links como /@canal/live apenas redirecionam para o vídeo de verdade.
        while info.get("_type") in _REDIRECT_TYPES:
            info = ydl.extract_info(info["url"], download=False, process=False)
        if info.get("_type") in _COLLECTION_TYPES:
            raise ExtractionError("Este link é de uma playlist ou de um canal. Cole o link de um único vídeo.")
        if info.get("live_status") == "is_live" or info.get("is_live"):
            raise ExtractionError("Não é possível extrair o áudio de uma transmissão ao vivo.")
        return info

    @staticmethod
    def _options(
        work_dir: Path,
        audio_format: AudioFormat,
        ffmpeg: str,
        on_progress: ProgressCallback,
        cancel: threading.Event,
    ) -> dict:
        def progress_hook(status: dict) -> None:
            if cancel.is_set():
                raise DownloadCancelled()
            if status["status"] == "downloading":
                total = status.get("total_bytes") or status.get("total_bytes_estimate")
                percent = status["downloaded_bytes"] / total * 100 if total else None
                on_progress(Progress(Stage.DOWNLOADING, percent))

        def postprocessor_hook(status: dict) -> None:
            if cancel.is_set():
                raise DownloadCancelled()
            if status["status"] == "started":
                on_progress(Progress(Stage.CONVERTING))

        postprocessor = {"key": "FFmpegExtractAudio", "preferredcodec": audio_format.codec}
        if audio_format.bitrate:
            postprocessor["preferredquality"] = audio_format.bitrate

        return {
            "format": "bestaudio/best",
            "noplaylist": True,
            "paths": {"home": str(work_dir)},
            "outtmpl": "%(title).150B.%(ext)s",
            "postprocessors": [postprocessor],
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "ffmpeg_location": ffmpeg,
            "js_runtimes": {"deno": {}, "node": {}},
            "logger": _SilentLogger(),
            "noprogress": True,
        }
