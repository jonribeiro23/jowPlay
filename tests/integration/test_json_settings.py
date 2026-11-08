import tempfile
import unittest
from pathlib import Path

from ytdown.infrastructure.json_settings import JsonSettings


class JsonSettingsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "config" / "settings.json"

    def test_values_survive_a_restart(self):
        JsonSettings(self.path).set("library_folder", "D:/Minhas músicas")
        settings = JsonSettings(self.path)
        self.assertEqual(settings.get("library_folder"), "D:/Minhas músicas")
        self.assertEqual(settings.get("volume", 0.8), 0.8)

    def test_unreadable_file_falls_back_to_defaults_and_can_be_fixed(self):
        self.path.parent.mkdir(parents=True)
        for content in ("{ quebrado", "[1, 2, 3]", ""):
            with self.subTest(content):
                self.path.write_text(content, encoding="utf-8")
                settings = JsonSettings(self.path)
                self.assertIsNone(settings.get("library_folder"))
                settings.set("library_folder", "C:/x")
                self.assertEqual(JsonSettings(self.path).get("library_folder"), "C:/x")

    def test_saving_leaves_no_temporary_files(self):
        settings = JsonSettings(self.path)
        for volume in range(5):
            settings.set("volume", volume)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["settings.json"])


if __name__ == "__main__":
    unittest.main()
