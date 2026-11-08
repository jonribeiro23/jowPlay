"""Página "Extrair": extrai o áudio de uma ou várias URLs do YouTube para a biblioteca.

A extração roda em um QThread; o trabalho em segundo plano conversa com a página
apenas por sinais Qt, que chegam à thread da interface.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QGuiApplication, QKeyEvent, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ytdown.application.extraction import ExtractBatch
from ytdown.application.library import RegisterExtractedTrack
from ytdown.domain.errors import ShareError
from ytdown.domain.library import DuplicatePolicy, Track
from ytdown.domain.models import (
    AUDIO_FORMATS,
    AudioFormat,
    AudioMetadata,
    BatchResult,
    Progress,
    Stage,
    is_valid_track_no,
    is_valid_year,
)
from ytdown.domain.urls import parse_url_list
from ytdown.presentation import texts
from ytdown.presentation.qt import theme

COVER_FILTER = "Imagens (*.jpg *.jpeg *.png *.webp *.bmp *.gif);;Todos os arquivos (*.*)"
EXTRACT_LABEL = "Extrair áudio"
CANCEL_LABEL = "Cancelar"

# Recebe os vídeos que já estão na biblioteca e devolve o que fazer, ou None para não extrair.
AskDuplicates = Callable[[list[tuple[str, Track]]], DuplicatePolicy | None]


def ask_duplicates_dialog(parent: QWidget) -> AskDuplicates:
    """Pergunta com "Substituir", "Manter os dois" e "Cancelar" (Esc também cancela)."""

    def ask(duplicates: list[tuple[str, Track]]) -> DuplicatePolicy | None:
        box = QMessageBox(QMessageBox.Icon.Question, texts.DUPLICATE_TITLE, texts.duplicate_question(duplicates),
                          parent=parent)
        replace = box.addButton(texts.REPLACE_LABEL, QMessageBox.ButtonRole.DestructiveRole)
        keep_both = box.addButton(texts.KEEP_BOTH_LABEL, QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton(texts.CANCEL_LABEL, QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep_both)  # O mais seguro: nada se perde.
        box.setEscapeButton(cancel)
        box.exec()
        return {replace: DuplicatePolicy.REPLACE, keep_both: DuplicatePolicy.KEEP_BOTH}.get(box.clickedButton())

    return ask


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

    def __init__(self, parent: QObject, extract_batch: ExtractBatch, urls, destination, audio_format, metadata,
                 cancel, number_tracks: bool) -> None:
        super().__init__(parent)
        self._job = (extract_batch, urls, destination, audio_format, metadata, cancel, number_tracks)

    def run(self) -> None:
        extract_batch, urls, destination, audio_format, metadata, cancel, number_tracks = self._job
        try:
            results = extract_batch(
                urls, destination, audio_format, metadata,
                on_progress=self.progress.emit, on_result=self.item_done.emit, cancel=cancel,
                number_tracks=number_tracks,
            )
        except Exception as exc:  # Sem console: todo erro precisa aparecer na página.
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(results)


class ExtractPage(QWidget):
    """Cada áudio extraído entra na biblioteca (`library`).

    `send_to_phone`, quando informado, recebe os arquivos salvos na última extração.
    `ask_duplicates` decide o que fazer com vídeos que já estão na biblioteca; por padrão, pergunta.
    `genre_suggestions` dá os gêneros sugeridos ao digitar (os que já existem na biblioteca).
    """

    extraction_finished = Signal()

    def __init__(
        self,
        extract_batch: ExtractBatch,
        library: RegisterExtractedTrack,
        send_to_phone: Callable[[list[Path]], None] | None = None,
        ask_duplicates: AskDuplicates | None = None,
        genre_suggestions: Callable[[], list[str]] = lambda: [],
    ) -> None:
        super().__init__()
        self.setObjectName("page-extract")
        self._extract_batch = extract_batch
        self._library = library
        self._ask_duplicates = ask_duplicates or ask_duplicates_dialog(self)
        self._genre_suggestions = genre_suggestions
        self._send_to_phone = send_to_phone
        self._cancel = threading.Event()
        self._thread: ExtractionThread | None = None
        self._working = False
        self._batch_size = 0
        self._running_format = AUDIO_FORMATS[0]
        self.saved_files: list[Path] = []

        self._build()
        self._show(texts.Message(texts.WELCOME))

    # --- montagem

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[theme.PAGE_MARGIN] * 4)
        layout.addWidget(self._title())
        layout.addLayout(self._source_and_format())
        self.library_info = QLabel()
        self.library_info.setObjectName("libraryInfo")
        self.library_info.setWordWrap(True)
        self.library_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.library_info)
        self.refresh_library_folder()
        layout.addWidget(self._details())
        self._refresh_batch_fields()
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
        title.setObjectName("pageTitle")  # Tamanho e cor vêm do tema.
        return title

    def _source_and_format(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.addWidget(QLabel("URLs do YouTube (uma por linha)"), 0, 0, 1, 2)
        self.urls = UrlBox()
        self.urls.setFixedHeight(self.urls.fontMetrics().lineSpacing() * 4 + 12)
        self.urls.textChanged.connect(self._refresh_batch_fields)
        self.urls.submitted.connect(self.start)
        grid.addWidget(self.urls, 1, 0)
        self.paste_button = QPushButton("Colar")
        self.paste_button.clicked.connect(self._paste_urls)
        grid.addWidget(self.paste_button, 1, 1, Qt.AlignmentFlag.AlignTop)

        grid.addWidget(QLabel("Formato"), 2, 0, 1, 2)
        self.format_box = QComboBox()
        self.format_box.addItems([f.label for f in AUDIO_FORMATS])
        grid.addWidget(self.format_box, 3, 0, 1, 2)
        return grid

    def _details(self) -> QGroupBox:
        """Nome, autor, álbum, gênero, ano, nº da faixa e capa; tudo opcional."""
        box = QGroupBox("Informações do áudio (opcional)")
        grid = QGridLayout(box)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)

        self.title_label = QLabel(texts.TITLE_LABEL_SINGLE)
        grid.addWidget(self.title_label, 0, 0, 1, 2)
        self.title_field = QLineEdit()
        grid.addWidget(self.title_field, 1, 0, 1, 2)

        grid.addWidget(QLabel("Autor (vazio: sem autor)"), 2, 0, 1, 2)
        self.artist_field = QLineEdit()
        grid.addWidget(self.artist_field, 3, 0, 1, 2)

        grid.addWidget(QLabel("Álbum"), 4, 0)
        grid.addWidget(QLabel("Gênero"), 4, 1)
        self.album_field = QLineEdit()
        grid.addWidget(self.album_field, 5, 0)
        self.genre_field = QLineEdit()
        self.genre_completer = QCompleter([], self.genre_field)
        self.genre_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.genre_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.genre_field.setCompleter(self.genre_completer)
        grid.addWidget(self.genre_field, 5, 1)

        grid.addLayout(self._year_and_number(), 6, 0, 1, 2)

        grid.addWidget(QLabel("Imagem de capa (vazio: imagem padrão)"), 7, 0, 1, 2)
        cover_row = QHBoxLayout()
        self.cover_field = QLineEdit()
        cover_row.addWidget(self.cover_field, stretch=1)
        self.cover_button = QPushButton("Procurar...")
        self.cover_button.clicked.connect(self._choose_cover)
        cover_row.addWidget(self.cover_button)
        grid.addLayout(cover_row, 8, 0, 1, 2)

        for field in (self.title_field, self.artist_field, self.album_field, self.genre_field, self.year_field,
                      self.track_field, self.cover_field):
            field.returnPressed.connect(self.start)
        return box

    def _year_and_number(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(QLabel("Ano"), 0, 0)
        self.track_label = QLabel(texts.TRACK_LABEL_SINGLE)
        grid.addWidget(self.track_label, 0, 1)
        self.year_field = QLineEdit()
        self.year_field.setMaxLength(4)
        self.year_field.setPlaceholderText("2024")
        self.year_field.setFixedWidth(self.year_field.fontMetrics().horizontalAdvance("00000") + 24)
        grid.addWidget(self.year_field, 1, 0)
        self.track_field = QLineEdit()
        self.track_field.setMaxLength(3)
        self.track_field.setFixedWidth(self.year_field.width())
        grid.addWidget(self.track_field, 1, 1)
        self.number_tracks_box = QCheckBox(texts.NUMBER_TRACKS_LABEL)
        self.number_tracks_box.toggled.connect(self._refresh_batch_fields)
        grid.addWidget(self.number_tracks_box, 1, 2)
        grid.setColumnStretch(2, 1)
        return grid

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
        self.send_button.clicked.connect(self._send_saved_files)
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

    def _refresh_batch_fields(self) -> None:
        """Com vários vídeos, um único nome ou nº para todos não faz sentido: o nome vem de cada
        vídeo e o nº, se pedido, segue a ordem da lista (a partir do nº digitado).
        """
        batch = self._is_batch()
        idle = not self.is_working()
        self.title_label.setText(texts.TITLE_LABEL_BATCH if batch else texts.TITLE_LABEL_SINGLE)
        self.title_field.setEnabled(not batch and idle)
        self.number_tracks_box.setVisible(batch)  # Com um vídeo só, numerar não faz sentido.
        self.number_tracks_box.setEnabled(idle)
        if not batch:
            self.track_label.setText(texts.TRACK_LABEL_SINGLE)
        else:
            self.track_label.setText(texts.TRACK_LABEL_NUMBERED if self._numbering() else texts.TRACK_LABEL_BATCH)
        self.track_field.setEnabled(self._track_number_applies() and idle)

    def refresh_genre_suggestions(self) -> None:
        self.genre_completer.model().setStringList(self._genre_suggestions())

    def _paste_urls(self) -> None:
        pasted = QGuiApplication.clipboard().text().strip()
        if not pasted:
            return
        current = self.urls.toPlainText()
        if current.strip() and not current.endswith("\n"):
            pasted = "\n" + pasted
        self.urls.setPlainText((current if current.strip() else "") + pasted)

    def refresh_library_folder(self) -> None:
        """A pasta pode mudar nas Opções; a página mostra sempre a atual. Os áudios da última
        extração foram junto, então "Mostrar arquivo" e o envio ao celular passam a usar o lugar novo.
        """
        folder = self._library.folder
        previous = getattr(self, "_shown_folder", folder)
        if folder != previous:
            self.saved_files = [folder / path.relative_to(previous) if path.is_relative_to(previous) else path
                                for path in self.saved_files]
        self._shown_folder = folder
        self.library_info.setText(texts.library_destination(str(folder)))

    def showEvent(self, event: QShowEvent) -> None:
        self.refresh_library_folder()
        self.refresh_genre_suggestions()
        super().showEvent(event)

    def _choose_cover(self) -> None:
        image, _ = QFileDialog.getOpenFileName(self, "Escolher imagem de capa", "", COVER_FILTER)
        if image:
            self.cover_field.setText(str(Path(image)))

    def _numbers(self) -> tuple[int | None, int | None] | texts.Message:
        """Ano e nº da faixa digitados, ou a mensagem explicando o que está errado."""
        year_text, track_text = self.year_field.text().strip(), self.track_field.text().strip()
        year = int(year_text) if year_text.isdigit() else None
        if year_text and (year is None or not is_valid_year(year)):
            return texts.INVALID_YEAR
        if not self._track_number_applies():
            return year, None  # Fila sem numeração: o campo está desativado e não vale.
        track_no = int(track_text) if track_text.isdigit() else None
        if track_text and (track_no is None or not is_valid_track_no(track_no)):
            return texts.INVALID_TRACK_NO
        return year, track_no

    def _is_batch(self) -> bool:
        return len(self._url_lines()) > 1

    def _numbering(self) -> bool:
        return self._is_batch() and self.number_tracks_box.isChecked()

    def _track_number_applies(self) -> bool:
        return not self._is_batch() or self._numbering()

    def _metadata(self, year: int | None, track_no: int | None) -> AudioMetadata:
        cover = self.cover_field.text().strip().strip('"')  # "Copiar como caminho" inclui aspas.
        return AudioMetadata(
            title=self.title_field.text().strip(),
            artist=self.artist_field.text().strip(),
            cover=Path(cover) if cover else None,
            album=self.album_field.text().strip(),
            genre=self.genre_field.text().strip(),
            year=year,
            track_no=track_no,
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
        numbers = self._numbers()
        if problem is None and isinstance(numbers, texts.Message):
            problem = numbers
        if problem:
            self._finish_progress(0)
            self._show(problem)
            return
        year, track_no = numbers

        # Pergunta uma vez, antes de baixar, o que fazer com vídeos que já estão na biblioteca.
        policy = DuplicatePolicy.KEEP_BOTH
        duplicates = self._library.find_duplicates(urls)
        if duplicates:
            policy = self._ask_duplicates(duplicates)
            if policy is None:
                self._finish_progress(0)
                self._show(texts.NOTHING_EXTRACTED)
                return

        self.refresh_library_folder()
        self._cancel.clear()
        self.saved_files = []
        self._batch_size = len(urls)
        self._running_format = self._selected_format()
        self._fill_queue(urls)
        self._set_working(True)
        starting = Progress(Stage.STARTING)
        self._set_progress(starting, texts.progress_text(starting, self._running_format))
        self._run_in_background(urls, self._library.destination(policy), self._running_format,
                                self._metadata(year, track_no), self._numbering())

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

    def _send_saved_files(self) -> None:
        try:
            self._send_to_phone(list(self.saved_files))
        except ShareError as exc:  # Ex.: a porta já está em uso por outro ytDown aberto.
            self._show(texts.Message(str(exc), texts.Tone.ERROR))

    # --- trabalho em segundo plano

    def _run_in_background(self, urls, destination, audio_format, metadata, number_tracks) -> None:
        self._thread = ExtractionThread(self, self._extract_batch, urls, destination, audio_format, metadata,
                                        self._cancel, number_tracks)
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
            for field in self._detail_fields():
                field.clear()
            self.number_tracks_box.setChecked(False)
        self.refresh_genre_suggestions()  # Um gênero novo já aparece como sugestão.
        self.show_file_button.setEnabled(bool(self.saved_files))
        self.send_button.setEnabled(bool(self.saved_files))
        self._finish_progress(texts.processed_percent(results))
        self._show(texts.result_summary(results, str(self._library.folder)))
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
        theme.set_tone(self.status, message.tone.name.lower())  # A cor vem do tema.

    def _detail_fields(self) -> list[QLineEdit]:
        return [self.title_field, self.artist_field, self.album_field, self.genre_field, self.year_field,
                self.track_field, self.cover_field]

    def _set_working(self, working: bool) -> None:
        self._working = working
        # Nome, nº da faixa e a opção de numerar dependem da fila: _refresh_batch_fields cuida deles.
        for widget in (self.urls, self.paste_button, self.format_box, self.artist_field, self.album_field,
                       self.genre_field, self.year_field, self.cover_field, self.cover_button):
            widget.setEnabled(not working)
        self.main_button.setText(CANCEL_LABEL if working else EXTRACT_LABEL)
        self.main_button.setEnabled(True)
        if working:
            self.show_file_button.setEnabled(False)
            self.send_button.setEnabled(False)
        self._refresh_batch_fields()
