"""Tema visual: cores só no tema, folha de estilo válida, ícones próprios, contraste e aplicação."""

import re
import unittest
from pathlib import Path

from tests.qt_support import dispose, qt_app
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel

from ytdown.infrastructure.resources import asset
from ytdown.presentation.qt import theme
from ytdown.presentation.qt.main_window import MainWindow
from ytdown.presentation.qt.navigation import LIBRARY_ICON, PAGE_ICONS

ROOT = Path(__file__).resolve().parents[2]
QT_CODE = ROOT / "ytdown" / "presentation" / "qt"
THEME_FOLDER = asset("theme")
STYLESHEET = THEME_FOLDER / theme.STYLESHEET_FILE
ICONS = THEME_FOLDER / theme.ICONS_FOLDER
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
TRANSPORT_ICONS = {"play", "pause", "previous", "next", "shuffle", "repeat", "volume", "mute", "queue", "options"}


def stylesheet_without_comments() -> str:
    return COMMENT.sub("", STYLESHEET.read_text(encoding="utf-8"))


def luminance(color: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(theme.COLORS[a]), luminance(theme.COLORS[b])), reverse=True)
    return (high + 0.05) / (low + 0.05)


class StylesheetTests(unittest.TestCase):
    def test_names_are_replaced_by_theme_values(self):
        rendered = theme.render_stylesheet("QLabel { color: {{text}}; padding: {{ space_s }}; }")
        self.assertEqual(rendered, f"QLabel {{ color: {theme.COLORS['text']}; padding: 8px; }}")

    def test_unknown_name_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "sem_cor"):
            theme.render_stylesheet("QLabel { color: {{sem_cor}}; }")

    def test_real_stylesheet_uses_only_theme_names(self):
        source = stylesheet_without_comments()
        self.assertEqual(HEX_COLOR.findall(source), [], "Cores devem vir de theme.COLORS")
        rendered = theme.render_stylesheet(source)
        self.assertNotIn("{{", rendered)

    def test_no_state_before_a_subcontrol(self):
        # "QSlider:focus::handle" faz o Qt aplicar a regra ao widget inteiro; o certo é "::handle:focus".
        self.assertEqual(re.findall(r":[a-z-]+::[a-z-]+", stylesheet_without_comments()), [])

    def test_icons_in_the_stylesheet_exist(self):
        for name in re.findall(r"url\(icons:([\w-]+)\.svg\)", stylesheet_without_comments()):
            with self.subTest(name):
                self.assertTrue((ICONS / f"{name}.svg").exists())


class NoFixedColorsInCodeTests(unittest.TestCase):
    def test_qt_screens_do_not_define_colors_or_font_sizes(self):
        for path in QT_CODE.glob("*.py"):
            if path.name == "theme.py":
                continue
            source = path.read_text(encoding="utf-8")
            with self.subTest(path.name):
                self.assertEqual(HEX_COLOR.findall(source), [])
                for forbidden in ("setStyleSheet", "QColor", "setPointSize", "setPixelSize"):
                    self.assertNotIn(forbidden, source)


class IconTests(unittest.TestCase):
    def test_every_icon_used_by_the_code_exists(self):
        for name in {*PAGE_ICONS.values(), LIBRARY_ICON, *TRANSPORT_ICONS}:
            with self.subTest(name):
                self.assertTrue((ICONS / f"{name}.svg").exists())

    def test_icons_are_svg_and_use_only_the_theme_icon_colors(self):
        allowed = {theme.COLORS["icon"], theme.COLORS["icon_muted"]}
        icons = sorted(ICONS.glob("*.svg"))
        self.assertTrue(icons)
        for path in icons:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path.name):
                self.assertTrue(source.startswith("<svg"))
                self.assertNotIn("<image", source)  # Desenho vetorial, sem imagem embutida.
                self.assertLessEqual(set(HEX_COLOR.findall(source)), allowed)


class ContrastTests(unittest.TestCase):
    """WCAG 2.1: 4,5:1 para texto e 3:1 para indicadores (foco) e textos grandes."""

    def test_text_is_readable_on_every_background(self):
        backgrounds = ("window", "surface", "surface_alt", "input", "nav", "pane_top", "pane_bottom",
                       "header_top", "bar_middle", "bar_bottom", "button_top", "button_bottom")
        for text in ("text", "text_muted"):
            for background in backgrounds:
                with self.subTest(text=text, background=background):
                    self.assertGreaterEqual(contrast(text, background), 4.5)

    def test_messages_are_readable(self):
        for tone in ("success", "error"):
            for background in ("surface", "window"):
                with self.subTest(tone=tone, background=background):
                    self.assertGreaterEqual(contrast(tone, background), 4.5)

    def test_selected_and_highlighted_text_is_readable(self):
        for background in ("selection_top", "selection_bottom", "accent_dark"):
            with self.subTest(background):
                self.assertGreaterEqual(contrast("text_on_accent", background), 4.5)
        self.assertGreaterEqual(contrast("accent_light", "window"), 4.5)  # Código de pareamento.

    def test_keyboard_focus_is_visible(self):
        for background in ("window", "surface", "input", "nav", "bar_middle", "selection_bottom",
                           "button_bottom"):
            with self.subTest(background):
                self.assertGreaterEqual(contrast("focus", background), 3)


class ApplyThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        style = self.app.style().name()
        self.addCleanup(self.restore, style)
        theme.apply_theme(self.app, THEME_FOLDER)

    def restore(self, style):
        """Os outros testes rodam sem tema, como antes."""
        self.app.setStyleSheet("")
        self.app.styleHints().unsetColorScheme()
        self.app.setPalette(QPalette())
        QApplication.setStyle(style)

    def test_uses_the_theme_palette_and_icons(self):
        self.assertEqual(self.app.palette().color(QPalette.ColorRole.Window).name(), theme.COLORS["window"])
        self.assertFalse(theme.icon("play").isNull())

    def test_message_tone_picks_the_theme_color(self):
        label = QLabel("mensagem")
        self.addCleanup(dispose, label)
        for tone, color in (("error", "error"), ("success", "success"), ("neutral", "text")):
            with self.subTest(tone):
                theme.set_tone(label, tone)
                label.ensurePolished()
                self.assertEqual(label.palette().color(QPalette.ColorRole.WindowText).name(), theme.COLORS[color])

    def test_main_window_has_icons(self):
        window = MainWindow()
        self.addCleanup(dispose, window)
        self.assertFalse(window.transport.play_button.icon().isNull())
        library = window.navigation.topLevelItem(0)
        self.assertFalse(library.icon(0).isNull())
        self.assertFalse(library.child(0).icon(0).isNull())


if __name__ == "__main__":
    unittest.main()
