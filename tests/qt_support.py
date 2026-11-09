"""Base para testes de interface Qt: uma QApplication em modo offscreen (sem abrir janelas na tela)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# O FFmpeg do Qt escreve informações dos arquivos no console; nos testes, isso só atrapalha.
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg*=false")

import time  # noqa: E402
from collections.abc import Callable  # noqa: E402

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402


def dispose(widget: QWidget) -> None:
    """Fecha e apaga o widget agora, com tudo o que estava pendente de exclusão.

    Sem isso, o Python destrói os widgets ao encerrar, às vezes depois da QApplication,
    e o processo cai (acesso inválido à memória) mesmo com todos os testes passando.
    """
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def qt_app() -> QApplication:
    """A QApplication do processo (só pode existir uma)."""
    return QApplication.instance() or QApplication([])


def pause(ms: int) -> None:
    """Deixa o Qt trabalhar por `ms` milissegundos, com um laço de eventos comum.

    Não use QTest.qWait: depois que o QtMultimedia avisa o fim de uma faixa, ele nunca mais
    volta (visto com o PySide6 6.12 no Windows), e o teste trava.
    """
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_until(condition: Callable[[], bool], timeout_ms: int = 5000) -> bool:
    """Processa eventos do Qt até `condition` ser verdadeira ou o tempo acabar.

    Equivale ao QTest.qWaitFor do C++, que o PySide6 não expõe.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if condition():
            return True
        pause(10)
    return condition()
