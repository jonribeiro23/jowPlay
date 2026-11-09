"""Diálogo modal: seleção explícita, progresso e ciclo de vida do worker."""
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QLabel, QListWidget, QProgressBar, QPushButton, QVBoxLayout, QPlainTextEdit


class ImportThread(QThread):
    progress = Signal(str, int, int)

    def __init__(self, parent, use_case, folders, cancel):
        super().__init__(parent)
        self.job = use_case, folders, cancel
        self.result = None
        self.error = None

    def run(self):
        try:
            use_case, folders, cancel = self.job
            self.result = use_case(folders, cancel, self.progress.emit)
        except Exception as exc:
            self.error = str(exc)


class ImportDialog(QDialog):
    import_finished = Signal()

    def __init__(self, use_case, is_busy=lambda: False, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Importar áudios extraídos...')
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.use_case, self.is_busy = use_case, is_busy
        self.thread = None
        self.cancel_event = Event()
        layout = QVBoxLayout(self)
        hint = QLabel('Escolha as pastas com áudios extraídos pelo ytDown antes da versão 2.0. '
                      'MP3, M4A, FLAC e WAV serão copiados, incluindo subpastas. Os originais serão mantidos.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.folders = QListWidget()
        layout.addWidget(self.folders)
        self.add_button = QPushButton('Adicionar pasta...')
        self.add_button.clicked.connect(self.choose_folder)
        layout.addWidget(self.add_button)
        self.remove_button = QPushButton('Remover pasta selecionada')
        self.remove_button.clicked.connect(lambda: self.folders.takeItem(self.folders.currentRow()))
        layout.addWidget(self.remove_button)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.status = QLabel('Selecione uma ou mais pastas de extrações anteriores.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.errors.hide()
        layout.addWidget(self.errors)
        self.start_button = QPushButton('Importar')
        self.start_button.clicked.connect(self.start)
        layout.addWidget(self.start_button)
        self.close_button = QPushButton('Fechar')
        self.close_button.clicked.connect(self.reject)
        layout.addWidget(self.close_button)
        self.resize(600, 440)

    def choose_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, 'Escolher pasta de áudios extraídos')
        if chosen and chosen not in [self.folders.item(i).text() for i in range(self.folders.count())]:
            self.folders.addItem(chosen)

    def is_working(self):
        return self.thread is not None

    def start(self):
        if self.is_working() or not self.folders.count():
            return
        if self.is_busy():
            self.status.setText('Aguarde a extração ou a mudança da pasta da biblioteca terminar.')
            return
        self.cancel_event.clear()
        self.errors.clear()
        self.errors.hide()
        self.start_button.setEnabled(False)
        self.add_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.close_button.setText('Cancelar')
        self.thread = ImportThread(self, self.use_case,
            [Path(self.folders.item(i).text()) for i in range(self.folders.count())], self.cancel_event)
        self.thread.progress.connect(self.on_progress)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def on_progress(self, phase, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.status.setText(f'{phase}: {done}/{total}' if total else phase)

    def on_finished(self):
        thread = self.thread
        thread.wait()
        result = thread.result
        self.thread = None
        thread.deleteLater()
        if thread.error:
            self.status.setText('Falha na importação: ' + thread.error)
        else:
            self.status.setText(('Importação cancelada. ' if result.cancelled else 'Importação concluída. ')
                + f'Importadas: {result.imported}; duplicadas: {result.duplicates}; erros: {len(result.errors)}.')
            self.errors.setPlainText('\n'.join(result.errors))
            self.errors.setVisible(bool(result.errors))
        self.start_button.setEnabled(True)
        self.add_button.setEnabled(True)
        self.remove_button.setEnabled(True)
        self.close_button.setText('Fechar')
        self.close_button.setEnabled(True)
        self.import_finished.emit()
        if getattr(self, '_closing', False):
            self.reject()

    def reject(self):
        if self.is_working():
            self.cancel_event.set()
            self.close_button.setEnabled(False)
            self.status.setText('Cancelando; aguardando limpeza dos arquivos temporários...')
            return
        super().reject()

    def closeEvent(self, event):
        if self.is_working():
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)

    def shutdown(self, on_done):
        if not self.is_working():
            return True
        self._closing = True
        self.import_finished.connect(on_done, Qt.ConnectionType.SingleShotConnection)
        self.reject()
        return False
