"""Janela principal: árvore de navegação | páginas | lista de reprodução, com a barra de controles embaixo."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRect, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QCloseEvent, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
LAST_PAGE_KEY = "navigation.last_page"

PageFactory = Callable[[PageId], QWidget]


class MainWindow(QMainWindow):
    import_requested = Signal()
    options_requested = Signal()
    closing = Signal()

    def __init__(self, page_factory: PageFactory = PlaceholderPage, settings=None) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(*MINIMUM_SIZE)
        self.resize(*DEFAULT_SIZE)
        self.settings = settings
        self._history: list[PageId] = []
        self._history_index = -1

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
        self.import_button = QToolButton()
        self.import_button.setText("Importar áudios extraídos...")
        self.import_button.setToolTip("Importar áudios extraídos...")
        self.import_button.clicked.connect(self.import_requested)
        side.addWidget(self.import_button)
        side.addWidget(self.options_button)

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        self.back_button = QToolButton()
        self.back_button.setText("←")
        self.back_button.setToolTip("Voltar")
        self.forward_button = QToolButton()
        self.forward_button.setText("→")
        self.forward_button.setToolTip("Avançar")
        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName("breadcrumb")
        header.addWidget(self.back_button)
        header.addWidget(self.forward_button)
        header.addWidget(self.breadcrumb, 1)
        self.search = QLineEdit()
        self.search.setObjectName("librarySearch")
        self.search.setPlaceholderText("Buscar músicas")
        self.search.setClearButtonEnabled(True)
        header.addWidget(self.search)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._apply_search)
        self.search.textChanged.connect(lambda: self._search_timer.start())
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        self._escape_search = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.search)
        self._escape_search.activated.connect(self._clear_search)
        content_layout.addLayout(header)
        content_layout.addWidget(self.pages, 1)
        self.back_button.clicked.connect(lambda: self._move_history(-1))
        self.forward_button.clicked.connect(lambda: self._move_history(1))

        self.splitter = QSplitter()
        self.splitter.setObjectName("mainSplitter")
        self.splitter.setChildrenCollapsible(False)
        for widget in (self.side_pane, self.content, self.play_queue):
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

        if settings is not None:
            geometry = settings.get("workspace.geometry")
            if isinstance(geometry, list) and len(geometry) == 4 and all(type(x) is int for x in geometry):
                x, y, w, h = geometry
                if (900 <= w <= 10000 and 560 <= h <= 10000 and abs(x) <= 10000 and abs(y) <= 10000
                        and any(screen.availableGeometry().intersects(QRect(x, y, w, h))
                                for screen in QGuiApplication.screens())):
                    self.setGeometry(x, y, w, h)
            sizes = settings.get("workspace.splitter")
            if isinstance(sizes, list) and len(sizes) == 3 and all(type(x) is int and 0 < x <= 10000 for x in sizes):
                self.splitter.setSizes(sizes)
            if settings.get("workspace.maximized") is True:
                self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

        self.navigation.page_selected.connect(self.show_page)
        self.transport.now_playing_requested.connect(lambda: self.show_page(PageId.NOW_PLAYING))
        self.transport.queue_pane_toggled.connect(self.play_queue.setVisible)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.transport.queue_toggle.toggle)
        saved = settings.get(LAST_PAGE_KEY) if settings is not None else None
        try:
            initial = PageId[saved] if isinstance(saved, str) else FIRST_PAGE
        except KeyError:
            initial = FIRST_PAGE
        self.show_page(initial)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Páginas com trabalho em andamento (ex.: extração) terminam antes de a janela fechar:
        a janela some na hora, e o app só encerra depois que elas limparem o que criaram.
        """
        waiting = [page for page in self._pages() if hasattr(page, "shutdown") and not page.shutdown(self.close)]
        if waiting:
            event.ignore()
            self.hide()
            return
        if self.settings is not None:
            rect = self.normalGeometry() if self.isMaximized() else self.geometry()
            self.settings.set("workspace.geometry", [rect.x(), rect.y(), rect.width(), rect.height()])
            self.settings.set("workspace.maximized", self.isMaximized())
            sizes = self.splitter.sizes()
            if all(size > 0 for size in sizes):
                self.settings.set("workspace.splitter", sizes)
        self.closing.emit()
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
        return (list(self._page_widgets.values()) + [self.transport] + getattr(self, "background_dialogs", [])
                + getattr(self, "background_jobs", []))

    def show_page(self, page: PageId) -> None:
        if self._history_index < 0 or self._history[self._history_index] != page:
            del self._history[self._history_index + 1:]
            self._history.append(page)
            self._history_index += 1
        self._display_page(page)

    def _display_page(self, page: PageId) -> None:
        self.pages.setCurrentIndex(self._page_index[page])
        searchable = callable(getattr(self._page_widgets[page], "set_search_text", None))
        self.search.setEnabled(searchable)
        self.search.setPlaceholderText("Buscar nesta página" if searchable else "Busca indisponível nesta página")
        if searchable:
            self._search_timer.stop()
            self._apply_search()
        if self.navigation.current_page() != page:
            self.navigation.blockSignals(True)
            try:
                self.navigation.select(page)
            finally:
                self.navigation.blockSignals(False)
        prefix = "Biblioteca › " if page in (PageId.SONGS, PageId.RECENT, PageId.ARTISTS, PageId.ALBUMS, PageId.GENRES) else ""
        detail = getattr(self._page_widgets[page], "current_key", None)
        self.breadcrumb.setText(prefix + page.title + (" › " + detail[0] if detail else ""))
        self.back_button.setEnabled(self._history_index > 0)
        self.forward_button.setEnabled(self._history_index < len(self._history) - 1)
        if self.settings is not None:
            self.settings.set(LAST_PAGE_KEY, page.name)

    def _move_history(self, offset: int) -> None:
        target = self._history_index + offset
        if 0 <= target < len(self._history):
            self._history_index = target
            self._display_page(self._history[target])

    def current_page(self) -> PageId:
        index = self.pages.currentIndex()
        return next(page for page, i in self._page_index.items() if i == index)

    def page(self, page: PageId) -> QWidget:
        return self._page_widgets[page]

    def _apply_search(self) -> None:
        handler = getattr(self.page(self.current_page()), "set_search_text", None)
        if callable(handler):
            handler(self.search.text())

    def _clear_search(self) -> None:
        self.search.clear()
        self._search_timer.stop()
        self._apply_search()
