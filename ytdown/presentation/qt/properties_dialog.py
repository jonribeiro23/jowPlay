"""Edição de propriedades individuais ou em lote."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ytdown.domain.errors import ExtractionError, LibraryError


class PropertiesDialog(QDialog):
    def __init__(self, tracks, edit, parent=None, cover_loader=None):
        super().__init__(parent)
        self.setWindowTitle("Propriedades")
        self.originals = list(tracks) if isinstance(tracks, (list, tuple)) else [tracks]
        self.track = self.originals[0]
        self.tracks = []
        self.edit = edit
        self.cover_loader = cover_loader
        self.fields, self.checks, self.initial, self.mixed = {}, {}, {}, set()
        self.cover_change = False
        self.cover = None
        layout = QVBoxLayout(self)
        if len(self.originals) > 1:
            layout.addWidget(QLabel("Selecione os campos que deseja aplicar a todas as faixas."))
        form = QFormLayout()
        layout.addLayout(form)
        labels = (("title", "Nome"), ("artist", "Artista"), ("album", "Álbum"),
                  ("genre", "Gênero"), ("year", "Ano"), ("track_no", "Número da faixa"))
        for name, label in labels:
            values = {getattr(track, name) for track in self.originals}
            mixed = len(values) > 1
            if mixed:
                self.mixed.add(name)
            initial = None if mixed else next(iter(values))
            self.initial[name] = initial
            if name in ("year", "track_no"):
                field = QSpinBox(self)
                field.setRange(-1, 9999)
                field.setSpecialValueText("Valores mistos" if mixed else "Sem valor")
                field.setValue(-1 if mixed or initial is None else initial)
                field.valueChanged.connect(lambda _value, n=name: self.checks[n].setChecked(True))
            else:
                field = QLineEdit(initial or "", self)
                if mixed:
                    field.setPlaceholderText("Valores mistos")
                field.textEdited.connect(lambda _value, n=name: self.checks[n].setChecked(True))
            self.fields[name] = field
            row = QWidget(self)
            box = QHBoxLayout(row)
            box.setContentsMargins(0, 0, 0, 0)
            check = QCheckBox("Alterar", row)
            check.setAccessibleName("Alterar " + label)
            self.checks[name] = check
            box.addWidget(check)
            box.addWidget(field)
            form.addRow(label, row)
        cover_row = QHBoxLayout()
        choose = QPushButton("Trocar capa…", self)
        remove = QPushButton("Remover capa", self)
        self.cover_label = QLabel("Manter capa atual", self)
        choose.clicked.connect(self.choose_cover)
        remove.clicked.connect(self.remove_cover)
        cover_row.addWidget(choose)
        cover_row.addWidget(remove)
        cover_row.addWidget(self.cover_label)
        layout.addLayout(cover_row)
        storage = getattr(edit, "storage", None)
        root = getattr(storage, "root", None)
        recovery = str(Path(root) / ".ytdown-recovery") if isinstance(root, (str, Path)) else ".ytdown-recovery"
        recovery_label = QLabel("Cópias de recuperação: " + recovery, self)
        recovery_label.setWordWrap(True)
        recovery_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(recovery_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolher capa", "", "Imagens (*.jpg *.jpeg *.png *.webp *.bmp)")
        if not path:
            return
        try:
            if self.cover_loader is None:
                raise ExtractionError("Não foi possível carregar a imagem de capa.")
            self.cover = self.cover_loader.load(Path(path))
        except ExtractionError as exc:
            QMessageBox.warning(self, "Capa inválida", str(exc))
            return
        self.cover_change = True
        self.cover_label.setText(Path(path).name)

    def remove_cover(self):
        self.cover_change = True
        self.cover = None
        self.cover_label.setText("Remover capa frontal")

    def save(self):
        changes = {}
        for name, field in self.fields.items():
            if not self.checks[name].isChecked():
                continue
            value = field.text() if isinstance(field, QLineEdit) else (field.value() if field.value() > 0 else None)
            if name in self.mixed or value != self.initial[name]:
                changes[name] = value
        if self.cover_change:
            changes["cover"] = self.cover
        if not changes:
            self.accept()
            return
        errors = []
        for track in {track.id: track for track in self.originals}.values():
            try:
                self.tracks.append(self.edit(track.id, changes))
            except LibraryError as exc:
                errors.append(f"{track.title}: {exc}")
        if self.tracks:
            self.track = self.tracks[0]
        if errors:
            QMessageBox.warning(self, "Falha ao editar propriedades", "\n".join(errors))
        if self.tracks or not errors:
            self.accept()
