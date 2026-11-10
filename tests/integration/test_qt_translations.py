"""Os textos do próprio Qt (botões padrão) aparecem em português."""

import unittest

from PySide6.QtWidgets import QDialogButtonBox, QMessageBox

from tests.qt_support import dispose, qt_app
from ytdown.presentation import texts
from ytdown.presentation.qt.translations import install_translations


class QtTranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        self.translators = install_translations(self.app)
        self.addCleanup(lambda: [self.app.removeTranslator(t) for t in self.translators])

    def test_standard_buttons_are_in_portuguese(self):
        self.assertTrue(self.translators, "a tradução do Qt (qtbase_pt_BR) não foi encontrada")
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
                               | QDialogButtonBox.StandardButton.Save)
        self.addCleanup(dispose, box)
        labels = [button.text().replace("&", "") for button in box.buttons()]
        self.assertIn("Cancelar", labels)
        self.assertIn("Salvar", labels)
        question = QMessageBox(QMessageBox.Icon.Question, "Excluir", "?",
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        self.addCleanup(question.deleteLater)  # Sim/Não sem botão de escape: close() é recusado.
        self.assertEqual(sorted(b.text().replace("&", "") for b in question.buttons()), ["Não", "Sim"])


class CountTextTests(unittest.TestCase):
    def test_singular_and_plural(self):
        self.assertEqual(texts.tracks_count(0), "0 faixas")
        self.assertEqual(texts.tracks_count(1), "1 faixa")
        self.assertEqual(texts.tracks_count(2), "2 faixas")
        self.assertEqual(texts.albums_count(1), "1 álbum")
        self.assertEqual(texts.albums_count(3), "3 álbuns")
        self.assertEqual(texts.delete_tracks_question(1), "Enviar 1 faixa para a Lixeira e removê-la da biblioteca?")
        self.assertEqual(texts.delete_tracks_question(2), "Enviar 2 faixas para a Lixeira e removê-las da biblioteca?")


if __name__ == "__main__":
    unittest.main()
