"""Verificação da biblioteca sem bloquear a janela de abertura."""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, QThread, Signal


class LibraryCheckThread(QThread):
    def __init__(self, parent: QObject, check) -> None:
        super().__init__(parent)
        self._check = check
        self.cancel = Event()
        self.result = None
        self.error: str | None = None

    def run(self) -> None:
        try:
            self.result = self._check(self.cancel)
        except Exception as exc:
            self.error = str(exc)


class LibraryCheck(QObject):
    """Mantém a thread viva e participa do fechamento coordenado da janela."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, check, parent: QObject) -> None:
        super().__init__(parent)
        self._thread = LibraryCheckThread(self, check)
        self._thread.finished.connect(self._finish)

    def start(self) -> None:
        self._thread.start()

    def is_working(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def shutdown(self, on_done) -> bool:
        if not self.is_working():
            return True
        self.finished.connect(on_done)
        self.failed.connect(lambda _reason: on_done())
        self._thread.cancel.set()
        return False

    def _finish(self) -> None:
        self._thread.wait()
        if self._thread.error:
            self.failed.emit(self._thread.error)
        else:
            self.finished.emit(self._thread.result)
