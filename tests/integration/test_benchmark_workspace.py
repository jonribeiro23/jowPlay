"""Exercita o cenário reduzido sem depender de dados ou preferências do usuário."""
import os
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from scripts.benchmark_workspace import run


class BenchmarkWorkspaceTests(unittest.TestCase):
    def test_reduced_scenario(self):
        result = run(12, 2)
        self.assertEqual(result['count'], 12)
        self.assertEqual(result['albums'], 12)
        self.assertEqual(result['artists'], 12)
        self.assertEqual(result['check']['checked'], 12)
        self.assertEqual(result['check']['errors'], 0)
        self.assertEqual(result['import']['imported'], 2)
        self.assertEqual(result['import']['errors'], [])
        self.assertIn('scroll_albums_20_steps', result['seconds'])

    def test_search_and_sort_do_not_refresh_other_library_pages(self):
        from ytdown.presentation.qt.albums_page import AlbumsPage
        with patch.object(AlbumsPage, 'refresh', autospec=True) as refresh:
            run(12, 0)
            # Navegação, busca e ordenação não alteram a biblioteca.
            self.assertEqual(refresh.call_count, 0)


if __name__ == '__main__':
    unittest.main()
