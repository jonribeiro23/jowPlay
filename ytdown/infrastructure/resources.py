"""Localiza os arquivos que acompanham o app, rodando pelo código ou empacotado."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# Empacotado pelo PyInstaller, os arquivos ficam em sys._MEIPASS; pelo código, na raiz do projeto.
_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def asset(name: str) -> Path:
    return _BASE / "assets" / name


def find_ffmpeg() -> str | None:
    """Prefere a cópia embutida no app empacotado; senão, procura no PATH."""
    if getattr(sys, "frozen", False):
        bundled = _BASE / "ffmpeg" / "ffmpeg.exe"
        if bundled.exists():
            return str(bundled)
    return shutil.which("ffmpeg")
