"""Página "Extrair": extrai o áudio de uma ou várias URLs do YouTube.

A extração roda em um QThread; o trabalho em segundo plano conversa com a página
apenas por sinais Qt, que chegam à thread da interface.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ytdown.application.extraction import ExtractBatch
from ytdown.domain.models import AUDIO_FORMATS, AudioFormat, AudioMetadata, BatchResult, Progress, Stage
from ytdown.domain.urls import parse_url_list
from ytdown.presentation import texts

TONE_COLORS = {texts.Tone.NEUTRAL: "", texts.Tone.SUCCESS: "#1b7f3b", texts.Tone.ERROR: "#b00020"}
COVER_FILTER = "Imagens (*.jpg *.jpeg *.png *.webp *.bmp *.gif);;Todos os arquivos (*.*)"
EXTRACT_LABEL = "Extrair áudio"
CANCEL_LABEL = "Cancelar"


class UrlBox(QPlainTextEdit):
    """Caixa de URLs: Enter pula linha, Ctrl+Enter pede a extração e Tab vai ao próximo campo."""

    submitted = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("urlBox")
        self.setTabChangesFocus(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class ExtractionThread(QThread):
    """Roda o ExtractBatch fora da thread da interface e avisa por sinais.

    O objeto QThread vive na thread da interface; só o `run()` roda na outra. Os
    sinais emitidos lá chegam à interface pela fila de eventos do Qt.
    """

    progress = Signal(int, object)  # índice do vídeo, Progress
    item_done = Signal(int, object)  # índice do vídeo, BatchResult
    succeeded = Signal(object)  # list[BatchResult]
    failed = Signal(str)  # Erro antes de começar a fila (ex.: capa inválida).

    def __init__(self, parent: QObject, extract_batch: ExtractBatch, urls, dest, audio_format, metadata,
                 cancel) -> None:
        super().__init__(parent)
        self._job = (extract_batch, urls, dest, audio_format, metadata, cancel)

    def run(self) -> None:
        extract_batch, urls, dest, audio_format, metadata, cancel = self._job
        try:
            results = extract_batch(
                urls, dest, audio_format, metadata,
                on_progress=self.progress.emit, on_result=self.item_done.emit, cancel=cancel,
            )
        except Exception as exc:  # Sem console: todo erro precisa aparecer na página.
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(results)


class ExtractPage(QWidget):
    """`send_to_phone`, quando informado, recebe os arquivos salvos na última extração."""

    extraction_finished = Signal()

    def __init__(
        self,
        extract_batch: ExtractBatch,
        send_to_phone: Callable[[list[Path]], None] | None = None,
        default_destination: str | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("page-extract")
        self._extract_batch = extract_batch
        self._send_to_phone = send_to_phone
        self._cancel = threading.Event()
        self._thread: ExtractionThread | None = None
        self._working = False
        self._batch_size = 0
        self._running_format = AUDIO_FORMATS[0]
        self.saved_files: list[Path] = []

        self._build(default_destination or texts.default_destination())
        self._show(texts.Message(texts.WELCOME))

    # --- montagem

    def _build(self, destination: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self._title())
        layout.addLayout(self._source_and_output(destination))
        layout.addWidget(self._details())
        layout.addWidget(self._queue_list(), stretch=1)
        self.progress = QProgressBar()
        self.progress.setObjectName("extractProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.status = QLabel()
        self.status.setObjectName("extractStatus")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        layout.addLayout(self._buttons())
        layout.addStretch()

    @staticmethod
    def _title() -> QLabel:
        title = QLabel("Extrair")
        title.setObjectName("pageTitle")
        font = title.font()
        font.setPointSizeF(font.pointSizeF() * 1.6)
        title.setFont(font)
        return title

    def _source_and_output(self, destination: str) -> QGridLayout:
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.addWidget(QLabel("URLs do YouTube (uma por linha)"), 0, 0, 1, 2)
        self.urls = UrlBox()
        self.urls.setFixedHeight(self.urls.fontMetrics().lineSpacing() * 4 + 12)
        self.urls.textChanged.connect(self._refresh_title_field)
        self.urls.submitted.connect(self.start)
        grid.addWidget(self.urls, 1, 0)
        self.paste_button = QPushButton("Colar")
        self.paste_button.clicked.connect(self._paste_urls)
        grid.addWidget(self.paste_button, 1, 1, Qt.AlignmentFlag.AlignTop)

        grid.addWidget(QLabel("Formato"), 2, 0, 1, 2)
        self.format_box = QComboBox()
        self.format_box.addItems([f.label for f in AUDIO_FORMATS])
        grid.addWidget(self.format_box, 3, 0, 1, 2)

        grid.addWidget(QLabel("Salvar em"), 4, 0, 1, 2)
        self.destination = QLineEdit(destination)
        self.destination.returnPressed.connect(self.start)
        grid.addWidget(self.destination, 5, 0)
        self.browse_button = QPushButton("Procurar...")
        self.browse_button.clicked.connect(self._choose_folder)
        grid.addWidget(self.browse_button, 5, 1)
        return grid

    def _details(self) -> QGroupBox:
        box = QGroupBox("Informações do áudio (opcional)")
        grid = QGridLayout(box)
        grid.setColumnStretch(0, 1)
        self.title_label = QLabel(texts.TITLE_LABEL_SINGLE)
        grid.addWidget(self.title_label, 0, 0, 1, 2)
        self.title_field = QLineEdit()
        grid.addWidget(self.title_field, 1, 0, 1, 2)
        grid.addWidget(QLabel("Autor (vazio: sem autor)"), 2, 0, 1, 2)
        self.artist_field = QLineEdit()
        grid.addWidget(self.artist_field, 3, 0, 1, 2)
        grid.addWidget(QLabel("Imagem de capa (vazio: imagem padrão)"), 4, 0, 1, 2)
        self.cover_field = QLineEdit()
        grid.addWidget(self.cover_field, 5, 0)
        self.cover_button = QPushButton("Procurar...")
        self.cover_button.clicked.connect(self._choose_cover)
        grid.addWidget(self.cover_button, 5, 1)
        for field in (self.title_field, self.artist_field, self.cover_field):
            field.returnPressed.connect(self.start)
        return box

    def _queue_list(self) -> QTreeWidget:
        """Situação de cada vídeo; aparece só quando há mais de um."""
        self.queue = QTreeWidget()
        self.queue.setObjectName("extractQueue")
        self.queue.setHeaderLabels(["Vídeo", "Situação"])
        self.queue.setRootIsDecorated(False)
        self.queue.setColumnWidth(0, 320)
        self.queue.hide()
        return self.queue

    def _buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()
        self.show_file_button = QPushButton("Mostrar arquivo")
        self.show_file_button.setEnabled(False)
        self.show_file_button.clicked.connect(self._show_file)
        row.addWidget(self.show_file_button)
        self.send_button = QPushButton("Enviar para o celular")
        self.send_button.setEnabled(False)
        self.send_button.setVisible(self._send_to_phone is not None)
        self.send_button.clicked.connect(lambda: self._send_to_phone(list(self.saved_files)))
        row.addWidget(self.send_button)
        self.main_button = QPushButton(EXTRACT_LABEL)
        self.main_button.setObjectName("extractButton")
        self.main_button.setDefault(True)
        self.main_button.clicked.connect(self._on_main_button)
        row.addWidget(self.main_button)
        return row

    # --- campos

    def _url_lines(self) -> list[str]:
        return [line for line in self.urls.toPlainText().splitlines() if line.strip()]

    def _refresh_title_field(self) -> None:
        """Com vários vídeos, um único nome para todos não faz sentido."""
        batch = len(self._url_lines()) > 1
        self.title_label.setText(texts.TITLE_LABEL_BATCH if batch else texts.TITLE_LABEL_SINGLE)
        self.title_field.setEnabled(not batch and not self.is_working())

    def _paste_urls(self) -> None:
        pasted = QGuiApplication.clipboard().text().strip()
        if not pasted:
            return
        current = self.urls.toPlainText()
        if current.strip() and not current.endswith("\n"):
            pasted = "\n" + pasted
        self.urls.setPlainText((current if current.strip() else "") + pasted)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Salvar áudio em", self.destination.text())
        if folder:
            self.destination.setText(str(Path(folder)))

    def _choose_cover(self) -> None:
        image, _ = QFileDialog.getOpenFileName(self, "Escolher imagem de capa", "", COVER_FILTER)
        if image:
            self.cover_field.setText(str(Path(image)))

    def _metadata(self) -> AudioMetadata:
        cover = self.cover_field.text().strip().strip('"')  # "Copiar como caminho" inclui aspas.
        return AudioMetadata(
            title=self.title_field.text().strip(),
            artist=self.artist_field.text().strip(),
            cover=Path(cover) if cover else None,
        )

    def _selected_format(self) -> AudioFormat:
        return AUDIO_FORMATS[self.format_box.currentIndex()]

    # --- ações

    def is_working(self) -> bool:
        return self._working

    def start(self) -> None:
        if self.is_working():
            return
        urls, invalid_lines = parse_url_list(self.urls.toPlainText())
        problem = texts.url_problem(urls, invalid_lines)
        dest = Path(self.destination.text().strip())
        if problem is None and not dest.is_absolute():
            problem = texts.INVALID_DESTINATION
        if problem:
            self._finish_progress(0)
            self._show(problem)
            return

        self._cancel.clear()
        self.saved_files = []
        self._batch_size = len(urls)
        self._running_format = self._selected_format()
        self._fill_queue(urls)
        self._set_working(True)
        starting = Progress(Stage.STARTING)
        self._set_progress(starting, texts.progress_text(starting, self._running_format))
        self._run_in_background(urls, dest, self._running_format, self._metadata())

    def cancel(self) -> None:
        if self.is_working():
            self._cancel.set()
            self.main_button.setEnabled(False)
            self._show(texts.Message(texts.CANCELLING))

    def shutdown(self, on_done: Callable[[], None]) -> bool:
        """Para a janela fechar. Devolve True se já pode fechar; senão, cancela a extração
        e chama `on_done` quando ela terminar (a extração apaga seus temporários ao sair).
        """
        if not self.is_working():
            return True
        self.extraction_finished.connect(on_done, Qt.ConnectionType.SingleShotConnection)
        self.cancel()
        return False

    def _on_main_button(self) -> None:
        if self.is_working():
            self.cancel()
        else:
            self.start()

    def _show_file(self) -> None:
        existing = [path for path in self.saved_files if path.exists()]
        if existing:
            subprocess.Popen(f'explorer /select,"{existing[-1]}"')

    # --- trabalho em segundo plano

    def _run_in_background(self, urls, dest, audio_format, metadata) -> None:
        self._thread = ExtractionThread(self, self._extract_batch, urls, dest, audio_format, metadata, self._cancel)
        self._thread.progress.connect(self._on_progress)
        self._thread.item_done.connect(self._on_item_done)
        self._thread.succeeded.connect(self._on_finished)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _stop_background(self) -> None:
        self._thread.wait()  # O run() já terminou (o sinal final é a última coisa que ele faz).
        self._thread.deleteLater()
        self._thread = None

    @Slot(int, object)
    def _on_progress(self, index: int, progress: Progress) -> None:
        if self._cancel.is_set():
            return
        fmt = self._running_format
        if self._batch_size == 1:
            self._set_progress(progress, texts.progress_text(progress, fmt))
            return
        self._set_progress(
            texts.queue_progress(index, self._batch_size, progress),
            texts.queue_progress_text(index, self._batch_size, progress, fmt),
        )
        item = self.queue.topLevelItem(index)
        item.setText(1, texts.progress_text(progress, fmt))
        self.queue.scrollToItem(item)

    @Slot(int, object)
    def _on_item_done(self, index: int, result: BatchResult) -> None:
        if self._batch_size == 1:
            return
        item = self.queue.topLevelItem(index)
        if result.path:
            item.setText(0, result.path.name)
        item.setText(1, texts.queue_status(result))
        item.setToolTip(1, texts.queue_status(result))  # A coluna corta textos longos.

    @Slot(object)
    def _on_finished(self, results: list[BatchResult]) -> None:
        self._stop_background()
        self._set_working(False)
        self.saved_files = [result.path for result in results if result.path]
        if self.saved_files:
            # Essas informações são destes vídeos; não podem ir para os próximos sem querer.
            for field in (self.title_field, self.artist_field, self.cover_field):
                field.clear()
        self.show_file_button.setEnabled(bool(self.saved_files))
        self.send_button.setEnabled(bool(self.saved_files))
        self._finish_progress(texts.processed_percent(results))
        self._show(texts.result_summary(results, self.destination.text().strip()))
        self.extraction_finished.emit()

    @Slot(str)
    def _on_failed(self, reason: str) -> None:
        self._stop_background()
        self._set_working(False)
        self._finish_progress(0)
        self._show(texts.extraction_failed(reason))
        self.extraction_finished.emit()

    # --- estado da página

    def _fill_queue(self, urls: list[str]) -> None:
        self.queue.clear()
        self.queue.setVisible(len(urls) > 1)
        if len(urls) > 1:
            for url in urls:
                QTreeWidgetItem(self.queue, [url, texts.QUEUED])

    def _set_progress(self, progress: Progress, text: str) -> None:
        if progress.percent is None:
            self.progress.setRange(0, 0)  # Animação de "trabalhando", sem porcentagem.
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(round(progress.percent))
        self._show(texts.Message(text))

    def _finish_progress(self, value: float) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(round(value))

    def _show(self, message: texts.Message) -> None:
        self.status.setText(message.text)
        self.status.setProperty("tone", message.tone.name.lower())  # Para o tema (JOW-18).
        color = TONE_COLORS[message.tone]
        self.status.setStyleSheet(f"color: {color};" if color else "")

    def _set_working(self, working: bool) -> None:
        self._working = working
        for widget in (self.urls, self.paste_button, self.format_box, self.destination, self.browse_button,
                       self.artist_field, self.cover_field, self.cover_button):
            widget.setEnabled(not working)
        self.main_button.setText(CANCEL_LABEL if working else EXTRACT_LABEL)
        self.main_button.setEnabled(True)
        if working:
            self.show_file_button.setEnabled(False)
            self.send_button.setEnabled(False)
        self._refresh_title_field()
