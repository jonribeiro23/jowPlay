"""Janela principal em Qt, testada em modo offscreen."""

import unittest

from tests.qt_support import qt_app
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from ytdown.presentation.qt.main_window import FIRST_PAGE, MINIMUM_SIZE, MainWindow
from ytdown.presentation.qt.navigation import LIBRARY_LABEL
from ytdown.presentation.qt.pages import PageId


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)
        self.addCleanup(self.window.close)

    def click_navigation(self, page: PageId):
        """Clica no item da árvore como um usuário faria."""
        tree = self.window.navigation
        item = tree._items[page]
        rect = tree.visualItemRect(item)
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())

    def test_has_the_four_areas(self):
        for widget in (self.window.navigation, self.window.pages, self.window.play_queue, self.window.transport):
            with self.subTest(widget.objectName()):
                self.assertTrue(widget.isVisible())

    def test_navigation_lists_every_page_under_library(self):
        tree = self.window.navigation
        library = tree.topLevelItem(0)
        self.assertEqual(library.text(0), LIBRARY_LABEL)
        self.assertEqual([library.child(i).text(0) for i in range(library.childCount())],
                         ["Músicas", "Artistas", "Álbuns", "Gêneros"])
        self.assertEqual([tree.topLevelItem(i).text(0) for i in range(1, tree.topLevelItemCount())],
                         ["Playlists", "Extrair"])

    def test_opens_on_the_first_page(self):
        self.assertEqual(self.window.current_page(), FIRST_PAGE)

    def test_clicking_the_tree_switches_the_page(self):
        for page in PageId:
            with self.subTest(page):
                self.click_navigation(page)
                self.assertEqual(self.window.current_page(), page)
                title = self.window.pages.currentWidget().findChild(QLabel, "pageTitle")
                self.assertEqual(title.text(), page.title)

    def test_clicking_the_library_group_keeps_the_current_page(self):
        self.window.show_page(PageId.ALBUMS)
        tree = self.window.navigation
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton,
                         pos=tree.visualItemRect(tree.topLevelItem(0)).center())
        self.assertEqual(self.window.current_page(), PageId.ALBUMS)

    def test_show_page_also_selects_it_in_the_tree(self):
        self.window.show_page(PageId.EXTRACT)
        self.assertEqual(self.window.navigation.current_page(), PageId.EXTRACT)

    def test_play_queue_pane_can_be_hidden_and_shown(self):
        toggle = self.window.transport.queue_toggle
        toggle.click()
        self.assertFalse(self.window.play_queue.isVisible())
        QTest.keyClick(self.window, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.window.play_queue.isVisible())
        self.assertTrue(toggle.isChecked())

    def test_controls_exist_but_have_no_action_yet(self):
        for control in self.window.transport.controls():
            with self.subTest(control.objectName()):
                self.assertFalse(control.isEnabled())

    def test_minimum_size_and_only_the_content_grows(self):
        self.assertEqual((self.window.minimumWidth(), self.window.minimumHeight()), MINIMUM_SIZE)
        before = self.window.splitter.sizes()
        self.window.resize(self.window.width() + 300, self.window.height())
        QTest.qWait(50)
        after = self.window.splitter.sizes()
        self.assertEqual((after[0], after[2]), (before[0], before[2]))
        self.assertEqual(after[1], before[1] + 300)


if __name__ == "__main__":
    unittest.main()
