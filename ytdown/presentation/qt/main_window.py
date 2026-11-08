"""Janela principal: árvore de navegação | páginas | lista de reprodução, com a barra de controles embaixo."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QSplitter, QStackedWidget, QVBoxLayout, QWidget

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
    def __init__(self, page_factory: PageFactory = PlaceholderPage) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(*MINIMUM_SIZE)
        self.resize(*DEFAULT_SIZE)

        self.navigation = NavigationPane()
        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        self._page_index: dict[PageId, int] = {}
        for page in PageId:
            self._page_index[page] = self.pages.addWidget(page_factory(page))
        self.play_queue = PlayQueuePane()
        self.transport = TransportBar()

        self.splitter = QSplitter()
        self.splitter.setObjectName("mainSplitter")
        self.splitter.setChildrenCollapsible(False)
        for widget in (self.navigation, self.pages, self.play_queue):
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

    def show_page(self, page: PageId) -> None:
        self.pages.setCurrentIndex(self._page_index[page])
        if self.navigation.current_page() != page:
            self.navigation.select(page)

    def current_page(self) -> PageId:
        index = self.pages.currentIndex()
        return next(page for page, i in self._page_index.items() if i == index)

    def page(self, page: PageId) -> QWidget:
        return self.pages.widget(self._page_index[page])
