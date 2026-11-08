"""Janela principal: árvore de navegação | páginas | lista de reprodução, com a barra de controles embaixo."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ytdown.presentation import texts
from ytdown.presentation.qt import theme
from ytdown.presentation.qt.navigation import NavigationPane
from ytdown.presentation.qt.pages import PageId, PlaceholderPage
from ytdown.presentation.qt.play_queue_pane import PlayQueuePane
from ytdown.presentation.qt.transport_bar import TransportBar

APP_TITLE = "ytDown"
MINIMUM_SIZE = (900, 560)
DEFAULT_SIZE = (1200, 760)
SPLITTER_SIZES = (200, 760, 240)  # Navegação, conteúdo, lista de reprodução.
FIRST_PAGE = PageId.SONGS

PageFactory = Callable[[PageId], QWidget]


class MainWindow(QMainWindow):
    options_requested = Signal()

    def __init__(self, page_factory: PageFactory = PlaceholderPage) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(*MINIMUM_SIZE)
        self.resize(*DEFAULT_SIZE)

        self.navigation = NavigationPane()
        self.options_button = QToolButton()
        self.options_button.setObjectName("optionsButton")
        self.options_button.setText(texts.OPTIONS_TITLE)
        self.options_button.setIcon(theme.icon("options"))
        size = theme.METRICS["nav_icon_size"]
        self.options_button.setIconSize(QSize(size, size))
        self.options_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.options_button.setToolTip("Pasta da biblioteca e outras preferências")
        self.options_button.clicked.connect(self.options_requested)
        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        self._page_index: dict[PageId, int] = {}
        self._page_widgets: dict[PageId, QWidget] = {}
        for page in PageId:
            widget = page_factory(page)
            self._page_widgets[page] = widget
            self._page_index[page] = self.pages.addWidget(self._scrollable(widget))
        self.play_queue = PlayQueuePane()
        self.transport = TransportBar()

        # A coluna da esquerda: a árvore e, embaixo, o botão de Opções.
        self.side_pane = QWidget()
        self.side_pane.setObjectName("sidePane")
        self.side_pane.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        side = QVBoxLayout(self.side_pane)
        side.setContentsMargins(0, 0, 0, theme.PANE_MARGIN)
        side.setSpacing(0)
        side.addWidget(self.navigation, stretch=1)
        side.addWidget(self.options_button)

        self.splitter = QSplitter()
        self.splitter.setObjectName("mainSplitter")
        self.splitter.setChildrenCollapsible(False)
        for widget in (self.side_pane, self.pages, self.play_queue):
            self.splitter.addWidget(widget)
        self.splitter.setStretchFactor(1, 1)  # Ao redimensionar, só o conteúdo cresce.
        self.splitter.setSizes(list(SPLITTER_SIZES))

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.splitter, stretch=1)
        layout.addWidget(self.transport)
        self.setCentralWidget(central)

        self.navigation.page_selected.connect(self.show_page)
        self.transport.queue_pane_toggled.connect(self.play_queue.setVisible)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.transport.queue_toggle.toggle)
        self.navigation.select(FIRST_PAGE)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Páginas com trabalho em andamento (ex.: extração) terminam antes de a janela fechar:
        a janela some na hora, e o app só encerra depois que elas limparem o que criaram.
        """
        waiting = [page for page in self._pages() if hasattr(page, "shutdown") and not page.shutdown(self.close)]
        if waiting:
            event.ignore()
            self.hide()
            return
        event.accept()

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        """Com a janela baixa, a página rola em vez de espremer os campos."""
        area = QScrollArea()
        area.setObjectName("pageScroll")
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(page)
        return area

    def _pages(self) -> list[QWidget]:
        return list(self._page_widgets.values())

    def show_page(self, page: PageId) -> None:
        self.pages.setCurrentIndex(self._page_index[page])
        if self.navigation.current_page() != page:
            self.navigation.select(page)

    def current_page(self) -> PageId:
        index = self.pages.currentIndex()
        return next(page for page, i in self._page_index.items() if i == index)

    def page(self, page: PageId) -> QWidget:
        return self._page_widgets[page]
