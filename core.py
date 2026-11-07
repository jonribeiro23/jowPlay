"""Lógica de extração de áudio. Não sabe nada sobre a interface gráfica."""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from mutagen import MutagenError
from yt_dlp.utils import DownloadCancelled, DownloadError

import tags

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


@dataclass(frozen=True)
class AudioFormat:
    label: str
    codec: str
    extension: str
    bitrate: str | None = None


AUDIO_FORMATS = (
    AudioFormat("MP3 - 192 kbps (recomendado)", "mp3", "mp3", "192"),
    AudioFormat("MP3 - 320 kbps", "mp3", "mp3", "320"),
    AudioFormat("MP3 - 128 kbps (arquivo menor)", "mp3", "mp3", "128"),
    AudioFormat("M4A (AAC) - 192 kbps", "m4a", "m4a", "192"),
    AudioFormat("FLAC (sem perda adicional)", "flac", "flac"),
    AudioFormat("WAV (sem compressão)", "wav", "wav"),
)


@dataclass(frozen=True)
class AudioMetadata:
    """Dados escolhidos pelo usuário. Vazio significa usar o valor padrão."""

    title: str = ""  # Padrão: título do vídeo.
    author: str = ""  # Padrão: sem autor.
    cover: Path | None = None  # Padrão: tags.DEFAULT_COVER.


@dataclass(frozen=True)
class Progress:
    """Atualização de progresso. `percent` é None quando o total é desconhecido."""

    message: str
    percent: float | None = None


class ExtractionError(Exception):
    """Falha com uma mensagem pronta para ser mostrada ao usuário."""


class ExtractionCancelled(Exception):
    pass


def is_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and parsed.hostname in YOUTUBE_HOSTS
    except ValueError:
        return False


def unique_path(path: Path) -> Path:
    """Devolve `path` ou, se já existir, `nome (1).ext`, `nome (2).ext`..."""
    candidate = path
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        counter += 1
    return candidate


def find_ffmpeg() -> str | None:
    """Prefere a cópia embutida no app empacotado; senão, procura no PATH."""
    if getattr(sys, "frozen", False):
        bundled = Path(sys._MEIPASS) / "ffmpeg" / "ffmpeg.exe"
        if bundled.exists():
            return str(bundled)
    return shutil.which("ffmpeg")


class _Logger:
    """Silencia o yt-dlp: um app com janela não tem console onde escrever."""

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def extract_audio(
    url: str,
    dest_dir: Path,
    audio_format: AudioFormat,
    on_progress: Callable[[Progress], None],
    cancel: threading.Event,
    metadata: AudioMetadata = AudioMetadata(),
) -> Path:
    """Baixa o áudio do vídeo, converte e devolve o caminho do arquivo salvo.

    Todo o trabalho acontece em uma pasta temporária, então uma falha ou um
    cancelamento nunca deixa arquivos pela metade em `dest_dir`.
    """
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise ExtractionError("O ffmpeg não foi encontrado neste computador.")

    # Lê a capa antes de baixar: uma imagem inválida deve falhar logo no início.
    try:
        cover = tags.load_cover(metadata.cover)
    except tags.InvalidCover as exc:
        raise ExtractionError(str(exc)) from exc

    def progress_hook(status: dict) -> None:
        if cancel.is_set():
            raise DownloadCancelled()
        if status["status"] == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            if total:
                percent = status["downloaded_bytes"] / total * 100
                on_progress(Progress(f"Baixando... {percent:.0f}%", percent))
            else:
                on_progress(Progress("Baixando..."))

    def postprocessor_hook(status: dict) -> None:
        if cancel.is_set():
            raise DownloadCancelled()
        if status["status"] == "started":
            on_progress(Progress(f"Convertendo para {audio_format.extension.upper()}..."))

    with tempfile.TemporaryDirectory(prefix="ytdown-", ignore_cleanup_errors=True) as temp:
        temp_dir = Path(temp)
        postprocessor = {"key": "FFmpegExtractAudio", "preferredcodec": audio_format.codec}
        if audio_format.bitrate:
            postprocessor["preferredquality"] = audio_format.bitrate

        options = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "paths": {"home": temp},
            "outtmpl": "%(title).150B.%(ext)s",
            "postprocessors": [postprocessor],
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "ffmpeg_location": ffmpeg,
            "js_runtimes": {"deno": {}, "node": {}},
            "logger": _Logger(),
            "noprogress": True,
        }

        on_progress(Progress("Obtendo informações do vídeo..."))
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                # process=False só lê os metadados, sem percorrer playlists inteiras.
                info = ydl.extract_info(url, download=False, process=False)
                # Links como /@canal/live apenas redirecionam para o vídeo de verdade.
                while info.get("_type") in ("url", "url_transparent"):
                    info = ydl.extract_info(info["url"], download=False, process=False)
                if info.get("_type") in ("playlist", "multi_video"):
                    raise ExtractionError(
                        "Este link é de uma playlist ou de um canal. Cole o link de um único vídeo."
                    )
                if info.get("live_status") == "is_live" or info.get("is_live"):
                    raise ExtractionError("Não é possível extrair o áudio de uma transmissão ao vivo.")
                ydl.process_ie_result(info, download=True)
        except DownloadCancelled as exc:
            raise ExtractionCancelled() from exc
        except DownloadError as exc:
            raise ExtractionError(str(exc).removeprefix("ERROR: ")) from exc

        if cancel.is_set():
            raise ExtractionCancelled()

        produced = sorted(temp_dir.glob(f"*.{audio_format.extension}"))
        if not produced:
            raise ExtractionError("A conversão terminou, mas o arquivo de áudio não foi gerado.")

        on_progress(Progress("Gravando nome, autor e capa..."))
        title = metadata.title or info.get("title") or produced[0].stem
        try:
            tags.write_tags(produced[0], title, metadata.author, cover)
        except (MutagenError, OSError) as exc:
            raise ExtractionError(f"Não foi possível gravar os metadados: {exc}") from exc

        on_progress(Progress("Salvando..."))
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            target = unique_path(dest_dir / produced[0].name)
            shutil.move(produced[0], target)
        except OSError as exc:
            raise ExtractionError(f"Não foi possível salvar em {dest_dir}: {exc}") from exc
        return target
