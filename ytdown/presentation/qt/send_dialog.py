"""Janela de compartilhamento; o servidor pertence à sessão do aplicativo."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ytdown.application.ports import ShareServer
from ytdown.presentation import texts
from ytdown.presentation.qt import theme

# Recebe a função a chamar quando algo muda (em outra thread) e devolve o servidor.
ShareServerFactory = Callable[[Callable[[], None]], ShareServer]

TITLE = "Enviar para o celular"
STEPS = (
    "1. Conecte o celular ao Wi-Fi da mesma rede deste PC.\n"
    "2. Abra o app jowPlay no celular e escolha este PC.\n"
    "3. Na primeira vez, digite o código abaixo no celular.\n"
    "4. Toque em Baixar no áudio que aparecer na lista."
)
FIREWALL_HINT = "Se o Windows perguntar, permita o acesso em redes privadas."
STOP_LABEL = "Parar de compartilhar"


class SendDialog(QDialog):
    """Janela não modal: dá para continuar extraindo com ela aberta.

    O servidor avisa as mudanças em threads próprias; o aviso vira um sinal Qt, que o
    Qt entrega na thread da interface antes de a lista ser atualizada.
    """

    sharing_stopped = Signal()
    _changed = Signal()

    def __init__(self, create_server: ShareServerFactory, parent: QWidget | None = None, managed: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("sendDialog")
        self.setWindowTitle(TITLE)
        self.setModal(False)
        self._stopped = False
        self._managed = managed
        self._changed.connect(self._refresh)
        self.server = create_server(self._notify_change)
        try:
            if not managed:
                self.server.start()
        except Exception:
            # Sem servidor a janela ficaria vazia e sem utilidade; ela nem chega a aparecer.
            self._stopped = True
            self.deleteLater()
            raise  # Quem abre a janela mostra a mensagem de erro.
        self._build()
        self.address.setText(texts.share_address(self.server.address()))
        self._refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[theme.PAGE_MARGIN] * 4)
        layout.addWidget(QLabel(STEPS))

        layout.addSpacing(theme.METRICS["space_s"])
        layout.addWidget(QLabel("Código de pareamento"))
        self.code = QLabel()
        self.code.setObjectName("pairingCode")  # Grande e em destaque pelo tema.
        self.code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.code)

        self.address = QLabel()
        self.address.setObjectName("shareAddress")
        self.address.setWordWrap(True)
        self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.address)

        layout.addSpacing(theme.METRICS["space_s"])
        layout.addWidget(QLabel("Áudios disponíveis para o celular"))
        self.files = QTreeWidget()
        self.files.setObjectName("sharedFiles")
        self.files.setHeaderLabels(["Arquivo", "Situação"])
        self.files.setRootIsDecorated(False)
        self.files.setColumnWidth(0, 320)
        self.files.setMinimumSize(540, 140)
        layout.addWidget(self.files, stretch=1)

        layout.addWidget(QLabel(FIREWALL_HINT))
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.stop_button = QPushButton(STOP_LABEL)
        if self._managed:
            self.stop_button.setText("Fechar")
        self.stop_button.setObjectName("stopSharing")
        self.stop_button.setAutoDefault(False)
        self.stop_button.clicked.connect(self.stop_sharing)
        buttons.addWidget(self.stop_button)
        layout.addLayout(buttons)

    def add(self, path: Path) -> None:
        self.server.share(path)
        self.show()
        self.raise_()
        self.activateWindow()

    def rows(self) -> list[tuple[str, str]]:
        return [(self.files.topLevelItem(i).text(0), self.files.topLevelItem(i).text(1))
                for i in range(self.files.topLevelItemCount())]

    def _notify_change(self) -> None:
        """Chamado pelo servidor, possivelmente em outra thread."""
        if self._stopped:
            return  # Uma conexão terminando depois do fim não tem mais onde aparecer.
        try:
            self._changed.emit()
        except RuntimeError:
            pass  # A janela já foi apagada pelo Qt.

    @Slot()
    def _refresh(self) -> None:
        if self._stopped:
            return
        self.code.setText(texts.pairing_code(self.server.pairing_code))
        self.files.clear()
        for name, status in self.server.statuses():
            QTreeWidgetItem(self.files, [name, texts.TRANSFER_STATUS[status]])

    def stop_sharing(self) -> None:
        """Para o servidor (inclusive as conexões abertas) e fecha a janela."""
        if self._stopped:
            return
        self._stopped = True
        if not self._managed:
            self.server.stop()
        self.sharing_stopped.emit()
        self.done(QDialog.DialogCode.Rejected)
        self.deleteLater()

    def reject(self) -> None:
        # Fechar a janela não encerra a sessão nem interrompe transferências.
        self.hide()


class PhoneSharing:
    """Mantém no máximo uma janela de envio: os áudios novos entram na lista da janela aberta."""

    def __init__(self, create_server: ShareServerFactory, parent: QWidget | None = None) -> None:
        self._create_server = create_server
        self.parent = parent
        self.dialog: SendDialog | None = None
        self.server = None

    def start(self) -> None:
        if self.server is None:
            server = self._create_server(self._notify_change)
            server.start()
            self.server = server

    def _notify_change(self) -> None:
        if self.dialog is not None:
            self.dialog._notify_change()

    def send(self, paths: list[Path]) -> None:
        """Pode lançar ShareError se o compartilhamento não iniciar (ex.: porta ocupada)."""
        if not paths:
            return
        if self.dialog is None:
            factory = (lambda _: self.server) if self.server is not None else self._create_server
            self.dialog = SendDialog(factory, self.parent, managed=self.server is not None)
            self.dialog.sharing_stopped.connect(self._on_stopped)
        for path in paths:
            self.dialog.add(path)

    def show_pairing(self) -> None:
        if self.dialog is None:
            factory = (lambda _: self.server) if self.server is not None else self._create_server
            self.dialog = SendDialog(factory, self.parent, managed=self.server is not None)
            self.dialog.sharing_stopped.connect(self._on_stopped)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def stop(self) -> None:
        if self.dialog is not None:
            self.dialog.stop_sharing()
        if self.server is not None:
            self.server.stop()
            self.server = None

    def _on_stopped(self) -> None:
        self.dialog = None
