"""Janela "Opções": por enquanto, a pasta da biblioteca.

Mudar a pasta move todos os áudios (ChangeLibraryFolder). Isso roda em um QThread, com
progresso; enquanto isso, a janela não fecha.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ytdown.domain.errors import LibraryError
from ytdown.presentation import texts
from ytdown.presentation.qt import theme

# (nova pasta, ao avançar(movidos, total)); falha com LibraryError sem mudar nada.
ChangeFolder = Callable[[Path, Callable[[int, int], None]], None]
ChooseFolder = Callable[[QWidget, Path], Path | None]


def choose_folder_dialog(parent: QWidget, current: Path) -> Path | None:
    chosen = QFileDialog.getExistingDirectory(parent, texts.LIBRARY_FOLDER_LABEL, str(current))
    return Path(chosen) if chosen else None


class RelocationThread(QThread):
    progress = Signal(int, int)
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject, change_folder: ChangeFolder, new_root: Path) -> None:
        super().__init__(parent)
        self._change_folder = change_folder
        self._new_root = new_root

    def run(self) -> None:
        try:
            self._change_folder(self._new_root, self.progress.emit)
        except LibraryError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # Sem console: todo erro precisa aparecer na janela.
            self.failed.emit(f"Erro inesperado: {exc}")
        else:
            self.succeeded.emit()


class OptionsDialog(QDialog):
    """`is_busy` diz se uma extração está em andamento: com ela, a pasta não pode mudar."""

    def __init__(
        self,
        library_folder: Callable[[], Path],
        change_folder: ChangeFolder,
        is_busy: Callable[[], bool] = lambda: False,
        parent: QWidget | None = None,
        choose_folder: ChooseFolder = choose_folder_dialog,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("optionsDialog")
        self.setWindowTitle(texts.OPTIONS_TITLE)
        self.setModal(True)  # Nada de extrair enquanto a biblioteca muda de lugar.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._library_folder = library_folder
        self._change_folder = change_folder
        self._is_busy = is_busy
        self._choose_folder = choose_folder
        self._thread: RelocationThread | None = None
        self._build()
        self._refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[theme.PAGE_MARGIN] * 4)
        title = QLabel(texts.LIBRARY_FOLDER_LABEL)
        title.setObjectName("paneTitle")
        layout.addWidget(title)
        hint = QLabel(texts.LIBRARY_FOLDER_HINT)
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        # Campo só de leitura: um caminho longo pode ser rolado e copiado, em vez de ficar cortado.
        self.folder = QLineEdit()
        self.folder.setObjectName("libraryFolder")
        self.folder.setReadOnly(True)
        row.addWidget(self.folder, stretch=1)
        self.change_button = QPushButton("Alterar...")
        self.change_button.clicked.connect(self.change)
        row.addWidget(self.change_button)
        layout.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        layout.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.close_button = QPushButton("Fechar")
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.setMinimumWidth(520)

    def _refresh(self) -> None:
        self.folder.setText(str(self._library_folder()))
        self.folder.setCursorPosition(0)  # Mostra o começo do caminho (a unidade).

    def is_moving(self) -> bool:
        return self._thread is not None

    def change(self) -> None:
        if self.is_moving():
            return
        if self._is_busy():
            self._show(texts.WAIT_FOR_EXTRACTION)
            return
        new_root = self._choose_folder(self, self._library_folder())
        if new_root is None:
            return
        self._set_moving(True)
        self._show(texts.Message(texts.moving_library(0, 0)))
        self._thread = RelocationThread(self, self._change_folder, new_root)
        self._thread.progress.connect(self._on_progress)
        self._thread.succeeded.connect(self._on_succeeded)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    @Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.status.setText(texts.moving_library(done, total))

    @Slot()
    def _on_succeeded(self) -> None:
        self._finish()
        self._show(texts.LIBRARY_MOVED)

    @Slot(str)
    def _on_failed(self, reason: str) -> None:
        self._finish()
        self._show(texts.library_move_failed(reason))

    def _finish(self) -> None:
        self._thread.wait()
        self._thread.deleteLater()
        self._thread = None
        self._set_moving(False)
        self._refresh()

    def _set_moving(self, moving: bool) -> None:
        self.change_button.setEnabled(not moving)
        self.close_button.setEnabled(not moving)
        self.progress.setVisible(moving)
        self.progress.setRange(0, 0)  # Animação até saber quantos arquivos são.

    def _show(self, message: texts.Message) -> None:
        self.status.setText(message.text)
        theme.set_tone(self.status, message.tone.name.lower())

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.is_moving():
            event.ignore()  # Fechar no meio deixaria a mudança sem acompanhamento.
            return
        super().closeEvent(event)

    def reject(self) -> None:  # Esc
        if not self.is_moving():
            super().reject()
