"""Cache descartável de capas, endereçado pelos bytes originais."""
from __future__ import annotations

import hashlib
import io
import logging
import os
import queue
import re
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageOps

from ytdown.application.ports import MetadataReader

_LOG = logging.getLogger(__name__)
_NAME = re.compile(r"[0-9a-f]{64}\.png\Z")


def default_thumbnail_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ytDown" / "thumbs"


class FileThumbnailCache:
    def __init__(self, reader: MetadataReader, directory: Path | None = None):
        self.reader = reader
        self.directory = directory or default_thumbnail_dir()
        self._lock = threading.RLock()
        self._jobs = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True, name="thumbnails")
        self._worker.start()

    def request(self, audio: Path) -> None:
        self._jobs.put(audio)

    def _run(self):
        while True:
            audio = self._jobs.get()
            try:
                if audio is None:
                    return
                self.get_or_create(audio)
            except Exception:
                _LOG.exception("Falha ao gerar miniatura de %s", audio)
            finally:
                self._jobs.task_done()

    def close(self):
        self._jobs.put(None)

    def _path(self, cover: bytes) -> Path:
        return self.directory / (hashlib.sha256(cover).hexdigest() + ".png")

    def get_or_create(self, audio: Path) -> Path | None:
        with self._lock:
            cover = self.reader.read_cover(audio)
            if not cover:
                return None
            target = self._path(cover)
            if target.is_file():
                return target
            with Image.open(io.BytesIO(cover)) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((200, 200), Image.Resampling.LANCZOS)
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                self.directory.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(prefix=".thumb-", suffix=".tmp", dir=self.directory)
                try:
                    with os.fdopen(fd, "wb") as output:
                        image.save(output, format="PNG")
                    os.replace(name, target)
                finally:
                    Path(name).unlink(missing_ok=True)
            return target

    def cleanup(self, audios) -> int:
        # Falha ao ler qualquer áudio impede toda exclusão: a referência pode existir nele.
        with self._lock:
            live = set()
            for audio in audios:
                cover = self.reader.read_cover(audio)
                if cover:
                    live.add(self._path(cover).name)
            if not self.directory.exists():
                return 0
            removed = 0
            for path in self.directory.iterdir():
                if _NAME.fullmatch(path.name) and path.name not in live and path.is_file() and not path.is_symlink():
                    path.unlink()
                    removed += 1
            return removed
