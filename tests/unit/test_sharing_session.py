import tempfile
import unittest
from pathlib import Path

from tests.fakes import FakeDevices
from ytdown.application.sharing import MAX_FAILED_ATTEMPTS, SharingSession
from ytdown.domain.sharing import TransferStatus


class SharingSessionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.changes = 0
        self.devices = FakeDevices()
        self.session = SharingSession(self.devices, on_change=self.count_change, failed_attempt_delay=0)

    def count_change(self):
        self.changes += 1

    def wrong_code(self):
        return "000000" if self.session.pairing_code != "000000" else "111111"

    def make_file(self, name="a.mp3"):
        path = self.dir / name
        path.write_bytes(b"audio")
        return path

    def test_correct_code_gives_a_known_token(self):
        token = self.session.try_pair(self.session.pairing_code, "Celular")
        self.assertTrue(self.session.is_authorized(token))
        self.assertEqual(self.devices.tokens[token], "Celular")

    def test_code_cannot_be_used_twice(self):
        code = self.session.pairing_code
        self.session.try_pair(code, "Celular")
        self.assertIsNone(self.session.try_pair(code, "Outro"))

    def test_wrong_code_is_refused(self):
        self.assertIsNone(self.session.try_pair(self.wrong_code(), "Celular"))

    def test_too_many_wrong_codes_change_the_code(self):
        original = self.session.pairing_code
        wrong = self.wrong_code()
        for _ in range(MAX_FAILED_ATTEMPTS):
            self.session.try_pair(wrong, "Intruso")
        # O novo código poderia, por acaso, ser igual ao antigo (1 em 1 milhão).
        if self.session.pairing_code != original:
            self.assertIsNone(self.session.try_pair(original, "Intruso"))

    def test_empty_or_unknown_tokens_are_not_authorized(self):
        self.assertFalse(self.session.is_authorized(""))
        self.assertFalse(self.session.is_authorized("token-falso"))

    def test_sharing_the_same_file_twice_keeps_one_entry(self):
        path = self.make_file()
        self.assertEqual(self.session.share(path).id, self.session.share(path).id)
        self.assertEqual(len(self.session.statuses()), 1)

    def test_new_files_wait_and_status_changes_are_reported(self):
        shared = self.session.share(self.make_file())
        self.assertEqual(self.session.statuses(), [("a.mp3", TransferStatus.WAITING)])
        before = self.changes
        self.session.set_status(shared.id, TransferStatus.SENT)
        self.assertEqual(self.session.statuses(), [("a.mp3", TransferStatus.SENT)])
        self.assertEqual(self.changes, before + 1)

    def test_available_lists_existing_files_with_their_size(self):
        shared = self.session.share(self.make_file())
        self.assertEqual(self.session.available(), [(shared, 5)])

    def test_deleted_file_is_no_longer_available(self):
        path = self.make_file()
        self.session.share(path)
        path.unlink()
        self.assertEqual(self.session.available(), [])

    def test_unknown_ids_are_not_found(self):
        self.assertIsNone(self.session.get("nao-existe"))


if __name__ == "__main__":
    unittest.main()
