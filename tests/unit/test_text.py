import unittest

from ytdown.domain.text import search_key


class SearchKeyTests(unittest.TestCase):
    def test_ignores_accents_and_case(self):
        self.assertEqual(search_key("AÇÃO"), "acao")
        self.assertEqual(search_key("Canção Número Ünico"), "cancao numero unico")

    def test_collapses_spaces(self):
        self.assertEqual(search_key("  Me   at\tthe zoo "), "me at the zoo")

    def test_compatibility_characters(self):
        self.assertEqual(search_key("ﬁnal"), "final")  # Ligadura "fi".
        self.assertEqual(search_key("Straße"), "strasse")  # casefold, não lower.

    def test_empty(self):
        self.assertEqual(search_key(""), "")


if __name__ == "__main__":
    unittest.main()
