import tempfile
import unittest
from pathlib import Path

from ytdown.infrastructure.sharing.device_store import JsonDeviceStore


class JsonDeviceStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "config" / "pairing.json"

    def test_identity_and_devices_survive_a_restart(self):
        store = JsonDeviceStore(self.path)
        token = store.add_device("Meu celular")
        reopened = JsonDeviceStore(self.path)
        self.assertEqual(reopened.server_id, store.server_id)
        self.assertTrue(reopened.knows(token))
        self.assertFalse(reopened.knows("token-falso"))

    def test_token_is_not_stored_in_plain_text(self):
        token = JsonDeviceStore(self.path).add_device("Meu celular")
        self.assertNotIn(token, self.path.read_text(encoding="utf-8"))

    def test_corrupted_file_starts_over(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{ quebrado", encoding="utf-8")
        self.assertTrue(JsonDeviceStore(self.path).server_id)


if __name__ == "__main__":
    unittest.main()
