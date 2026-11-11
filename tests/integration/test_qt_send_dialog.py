"""Janela "Enviar para o celular" em Qt, com o servidor real em portas livres (modo offscreen)."""

import http.client
import json
import tempfile
import unittest
from pathlib import Path

from tests.qt_support import dispose, qt_app, wait_until
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from tests.fakes import FakeDevices, FakeLibrary
from ytdown.application.sharing import SharingSession
from ytdown.domain.errors import ShareError
from ytdown.infrastructure.sharing.server import LocalShareServer
from ytdown.presentation.qt.extract_page import ExtractPage
from ytdown.presentation.qt.send_dialog import PhoneSharing, SendDialog

WAITING = "Aguardando o celular"


def free_port_server(on_change):
    return LocalShareServer(SharingSession(FakeDevices(), on_change, failed_attempt_delay=0),
                            http_port=0, discovery_port=0)


def flush_deletions():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def send_dialogs():
    return [w for w in QApplication.topLevelWidgets() if isinstance(w, SendDialog)]


class Phone:
    """Faz o papel do app do celular: as mesmas requisições, pela rede local do próprio PC."""

    def __init__(self, test: unittest.TestCase, port: int) -> None:
        self.connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        test.addCleanup(self.connection.close)
        self.token = None

    def request(self, method, path, body=None):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        self.connection.request(method, path, body=json.dumps(body) if body else None, headers=headers)
        response = self.connection.getresponse()
        return response.status, response.read()

    def pair(self, code):
        status, content = self.request("POST", "/api/pair", {"code": code, "device": "Celular de teste"})
        self.token = json.loads(content)["token"]
        return status


class SendDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)

    def open_dialog(self):
        dialog = SendDialog(free_port_server)
        self.addCleanup(flush_deletions)
        self.addCleanup(dialog.stop_sharing)
        return dialog

    def audio(self, name, content=b"audio" * 1000):
        path = self.dir / name
        path.write_bytes(content)
        return path

    def test_no_empty_window_is_left_when_sharing_cannot_start(self):
        busy = free_port_server(lambda: None)
        busy.start()
        self.addCleanup(busy.stop)

        def same_ports(on_change):
            return LocalShareServer(SharingSession(FakeDevices(), on_change),
                                    http_port=busy.port, discovery_port=busy.discovery_port)

        with self.assertRaises(ShareError):
            SendDialog(same_ports)
        flush_deletions()
        self.assertEqual(send_dialogs(), [])

    def test_shows_code_address_and_files(self):
        dialog = self.open_dialog()
        dialog.add(Path("a.mp3"))
        dialog.add(Path("b.mp3"))

        self.assertFalse(dialog.isModal())
        self.assertTrue(dialog.isVisible())
        code = dialog.server.pairing_code
        self.assertEqual(dialog.code.text(), f"{code[:3]} {code[3:]}")
        self.assertIn(f":{dialog.server.port}", dialog.address.text())
        self.assertEqual(dialog.rows(), [("a.mp3", WAITING), ("b.mp3", WAITING)])

    def test_changes_made_by_the_server_threads_reach_the_window(self):
        dialog = self.open_dialog()
        dialog.add(self.audio("música.mp3"))
        old_code = dialog.code.text()

        phone = Phone(self, dialog.server.port)
        self.assertEqual(phone.pair(dialog.server.pairing_code), 200)
        # O código muda depois de cada pareamento; quem avisa é a thread do servidor.
        self.assertTrue(wait_until(lambda: dialog.code.text() != old_code))

        status, listing = phone.request("GET", "/api/files")
        shared = json.loads(listing)["files"][0]
        self.assertEqual((status, shared["name"]), (200, "música.mp3"))
        self.assertEqual(phone.request("GET", f"/api/files/{shared['id']}")[0], 200)
        self.assertTrue(wait_until(lambda: dialog.rows() == [("música.mp3", "Enviado")]), dialog.rows())

    def test_stop_sharing_cuts_open_connections_and_closes_the_window(self):
        dialog = self.open_dialog()
        stopped = []
        dialog.sharing_stopped.connect(lambda: stopped.append(True))
        dialog.add(self.audio("a.mp3"))
        phone = Phone(self, dialog.server.port)
        phone.pair(dialog.server.pairing_code)
        self.assertEqual(phone.request("GET", "/api/files")[0], 200)

        dialog.stop_button.click()

        self.assertEqual(stopped, [True])
        self.assertTrue(dialog.server.stopping)
        self.assertFalse(dialog.isVisible())
        # A mesma conexão (keep-alive) não pode continuar sendo atendida.
        with self.assertRaises((OSError, http.client.HTTPException)):
            phone.request("GET", "/api/files")

    def test_closing_the_window_keeps_sharing(self):
        dialog = self.open_dialog()
        dialog.add(Path("a.mp3"))
        dialog.close()
        self.assertFalse(dialog.server.stopping)
        self.assertFalse(dialog.isVisible())
        phone = Phone(self, dialog.server.port)
        self.assertEqual(phone.pair(dialog.server.pairing_code), 200)
        self.assertEqual(phone.request("GET", "/api/files")[0], 200)


class PhoneSharingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        self.created = []

        def factory(on_change):
            server = free_port_server(on_change)
            self.created.append(server)
            return server

        self.sharing = PhoneSharing(factory)
        self.addCleanup(flush_deletions)
        self.addCleanup(self.sharing.stop)

    def test_new_audios_go_to_the_window_that_is_already_open(self):
        self.sharing.send([Path("a.mp3")])
        first = self.sharing.dialog
        self.sharing.send([Path("b.mp3"), Path("a.mp3")])
        self.assertIs(self.sharing.dialog, first)
        self.assertEqual(len(self.created), 1)
        self.assertEqual([name for name, _ in first.rows()], ["a.mp3", "b.mp3"])

    def test_after_stopping_a_new_window_starts_a_new_sharing(self):
        self.sharing.send([Path("a.mp3")])
        self.sharing.dialog.stop_button.click()
        self.assertIsNone(self.sharing.dialog)
        self.sharing.send([Path("b.mp3")])
        self.assertEqual(len(self.created), 2)
        self.assertEqual(self.sharing.dialog.rows(), [("b.mp3", WAITING)])

    def test_nothing_opens_without_audios(self):
        self.sharing.send([])
        self.assertIsNone(self.sharing.dialog)
        self.assertEqual(self.created, [])

    def test_close_reopen_and_application_shutdown(self):
        self.sharing.send([Path("a.mp3")])
        dialog = self.sharing.dialog
        server = dialog.server
        dialog.close()
        self.sharing.send([Path("b.mp3")])
        self.assertIs(self.sharing.dialog, dialog)
        self.assertEqual(len(self.created), 1)
        self.assertEqual([name for name, _ in dialog.rows()], ["a.mp3", "b.mp3"])
        self.sharing.stop()
        self.assertTrue(server.stopping)


class ExtractPageSendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_sharing_error_is_shown_on_the_page(self):
        def send_to_phone(_paths):
            raise ShareError("Não foi possível iniciar o compartilhamento.")

        page = ExtractPage(None, FakeLibrary(), send_to_phone=send_to_phone)
        self.addCleanup(dispose, page)
        page.saved_files = [Path("a.mp3")]
        page.send_button.setEnabled(True)
        page.send_button.click()
        self.assertEqual(page.status.text(), "Não foi possível iniciar o compartilhamento.")
        self.assertEqual(page.status.property("tone"), "error")

    def test_send_button_hands_over_the_saved_files(self):
        sent = []
        page = ExtractPage(None, FakeLibrary(), send_to_phone=sent.append)
        self.addCleanup(dispose, page)
        page.saved_files = [Path("a.mp3"), Path("b.mp3")]
        page.send_button.setEnabled(True)
        page.send_button.click()
        self.assertEqual(sent, [[Path("a.mp3"), Path("b.mp3")]])


if __name__ == "__main__":
    unittest.main()
