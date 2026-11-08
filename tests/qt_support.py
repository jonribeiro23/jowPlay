"""Base para testes de interface Qt: uma QApplication em modo offscreen (sem abrir janelas na tela)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# O FFmpeg do Qt escreve informações dos arquivos no console; nos testes, isso só atrapalha.
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg*=false")

from PySide6.QtWidgets import QApplication  # noqa: E402


def qt_app() -> QApplication:
    """A QApplication do processo (só pode existir uma)."""
    return QApplication.instance() or QApplication([])
