"""Tema visual do app, inspirado no Windows Media Player do Windows 7: fundo escuro, azul e preto
com gradientes e a barra de controles em destaque.

Todas as cores e espaçamentos ficam aqui. A folha de estilo (`assets/theme/ytdown.qss`) só usa
nomes como `{{accent}}`, trocados por estes valores ao carregar; o resto do código não define cor.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QWidget

COLORS: dict[str, str] = {
    # Fundos, do mais escuro ao mais claro.
    "window": "#0a0f17",
    "surface": "#0f1724",
    "surface_alt": "#141f30",
    "input": "#0b121d",
    "border": "#2a3b55",
    "border_light": "#3c5374",
    # Árvore de navegação (fundo sólido: o recuo dos itens é pintado com esta cor).
    "nav": "#132034",
    # Painéis com gradiente (lista de reprodução, cabeçalhos).
    "pane_top": "#18263a",
    "pane_bottom": "#0c1420",
    "header_top": "#26374f",
    "header_bottom": "#152234",
    # Barra de controles: preto brilhante.
    "bar_top": "#323d4d",
    "bar_middle": "#131922",
    "bar_bottom": "#04070b",
    # Botões.
    "button_top": "#2c3d57",
    "button_bottom": "#18233a",
    "button_hover_top": "#3a5375",
    "button_hover_bottom": "#203152",
    # Azul de destaque.
    "accent": "#3b8fe8",
    "accent_light": "#86c8ff",
    "accent_dark": "#17467f",
    "selection_top": "#2f72c0",
    "selection_bottom": "#1a4a86",
    "focus": "#8fd3ff",
    # Botão de tocar: esfera azul.
    "play_top": "#9ad8ff",
    "play_middle": "#2d8be3",
    "play_bottom": "#0a3a78",
    # Texto.
    "text": "#e8eef6",
    "text_muted": "#a3b3c8",
    "text_disabled": "#647389",
    "text_on_accent": "#ffffff",
    # Situação de uma mensagem (texts.Tone).
    "success": "#63d991",
    "error": "#ff8088",
    # Ícones (assets/theme/icons/*.svg usam só estas duas).
    "icon": "#e8eef6",
    "icon_muted": "#a3b3c8",
}

# Espaçamentos e tamanhos, em pixels independentes da escala do Windows.
METRICS: dict[str, int] = {
    "space_xs": 4,
    "space_s": 8,
    "space_m": 12,
    "space_l": 16,
    "radius": 3,
    "radius_l": 6,
    "button_size": 34,
    "play_button_size": 52,
    "icon_size": 20,
    "play_icon_size": 26,
    "nav_icon_size": 18,
}

PAGE_MARGIN = METRICS["space_l"]
PANE_MARGIN = METRICS["space_s"]

STYLESHEET_FILE = "ytdown.qss"
ICONS_FOLDER = "icons"
ICON_PREFIX = "icons"  # QIcon("icons:play.svg") procura na pasta registrada por apply_theme.

_TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_stylesheet(template: str) -> str:
    """Troca `{{nome}}` pela cor ou medida do tema; um nome desconhecido é erro, não estilo perdido."""
    values = {**COLORS, **{name: f"{value}px" for name, value in METRICS.items()}}

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in values:
            raise ValueError(f"Nome desconhecido na folha de estilo: {name}")
        return values[name]

    return _TOKEN.sub(replace, template)


def palette() -> QPalette:
    """Cores básicas para o que o Qt desenha sem a folha de estilo (menus, diálogos, seleção)."""
    roles = {
        QPalette.ColorRole.Window: "window",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "input",
        QPalette.ColorRole.AlternateBase: "surface_alt",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.PlaceholderText: "text_disabled",
        QPalette.ColorRole.Button: "button_bottom",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.Highlight: "selection_top",
        QPalette.ColorRole.HighlightedText: "text_on_accent",
        QPalette.ColorRole.ToolTipBase: "surface_alt",
        QPalette.ColorRole.ToolTipText: "text",
        QPalette.ColorRole.Link: "accent_light",
        QPalette.ColorRole.BrightText: "error",
    }
    result = QPalette()
    for role, name in roles.items():
        result.setColor(role, QColor(COLORS[name]))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        result.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS["text_disabled"]))
    return result


def apply_theme(app: QApplication, theme_folder: Path) -> None:
    """Aplica o tema ao app inteiro. `theme_folder` tem a folha de estilo e a pasta de ícones."""
    app.setStyle("Fusion")  # Desenha tudo pelo Qt, igual em qualquer versão do Windows.
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)  # Barra de título escura no Windows.
    app.setPalette(palette())
    QDir.setSearchPaths(ICON_PREFIX, [str(theme_folder / ICONS_FOLDER)])
    app.setStyleSheet(render_stylesheet((theme_folder / STYLESHEET_FILE).read_text(encoding="utf-8")))


def icon(name: str) -> QIcon:
    """Ícone do tema. Em SVG, fica nítido em qualquer escala; sem o tema carregado, vem vazio."""
    return QIcon(f"{ICON_PREFIX}:{name}.svg")


def set_tone(widget: QWidget, tone: str) -> None:
    """Muda a propriedade `tone` (neutral, success, error) que a folha de estilo usa para a cor."""
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)  # A folha de estilo só relê propriedades ao repolir.
    widget.style().polish(widget)
