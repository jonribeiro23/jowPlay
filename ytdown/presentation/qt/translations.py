"""Textos do próprio Qt em português: botões padrão (OK, Cancelar, Sim, Não, Salvar), menus de
edição dos campos de texto e diálogos de arquivo. Sem isso eles aparecem em inglês.
"""

from __future__ import annotations

from pathlib import Path

import PySide6
from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

LOCALE = QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil)
CATALOGS = ("qtbase", "qtmultimedia")


def translation_folders() -> list[Path]:
    """Onde o Qt costuma estar: a pasta do Qt instalado e, no app empacotado, a do PySide6."""
    folders = [Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)),
               Path(PySide6.__file__).parent / "translations"]
    return [folder for folder in dict.fromkeys(folders) if folder.is_dir()]


def install_translations(app: QCoreApplication) -> list[QTranslator]:
    """Instala as traduções encontradas e devolve os tradutores (para removê-los, nos testes)."""
    QLocale.setDefault(LOCALE)
    installed = []
    for catalog in CATALOGS:
        for folder in translation_folders():
            translator = QTranslator(app)
            if translator.load(LOCALE, catalog, "_", str(folder)):
                app.installTranslator(translator)
                installed.append(translator)
                break
    return installed
