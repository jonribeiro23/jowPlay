"""Testa o servidor com conexões reais, usando apenas o próprio computador."""

import http.client
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import share


def free_port(kind: int) -> int:
    with socket.socket(socket.AF_INET, kind) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class ShareServerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.store = self.dir / "config" / "pairing.json"
        delay = mock.patch.object(share, "FAILED_PAIR_DELAY", 0)
        delay.start()
        self.addCleanup(delay.stop)
        self.server = self.start_server()

    def start_server(self):
        server = share.ShareServer(store_path=self.store)
        self.udp_port = free_port(socket.SOCK_DGRAM)
        server.start(http_port=free_port(socket.SOCK_STREAM), discovery_port=self.udp_port)
        self.addCleanup(server.stop)
        return server

    def request(self, method, path, token=None, body=None, raw_body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        self.addCleanup(connection.close)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        data = raw_body if raw_body is not None else (json.dumps(body) if body is not None else None)
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()

    def pair(self):
        status, content = self.request(
            "POST", "/api/pair", body={"code": self.server.pairing_code, "device": "Meu celular"}
        )
        self.assertEqual(status, 200)
        return json.loads(content)["token"]

    def make_file(self, name="música.mp3", content=b"audio" * 50_000):
        path = self.dir / name
        path.write_bytes(content)
        return path, content

    def test_correct_code_gives_a_working_token(self):
        token = self.pair()
        status, content = self.request("GET", "/api/files", token)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content), {"files": []})

    def test_code_cannot_be_used_twice(self):
        old_code = self.server.pairing_code
        self.pair()
        status, _ = self.request("POST", "/api/pair", body={"code": old_code, "device": "Outro"})
        self.assertEqual(status, 403)

    def test_wrong_code_is_refused(self):
        wrong = "000000" if self.server.pairing_code != "000000" else "111111"
        status, content = self.request("POST", "/api/pair", body={"code": wrong})
        self.assertEqual(status, 403)
        self.assertNotIn(b"token", content)

    def test_too_many_wrong_codes_change_the_code(self):
        original = self.server.pairing_code
        wrong = "000000" if original != "000000" else "111111"
        for _ in range(share.MAX_PAIR_ATTEMPTS):
            self.request("POST", "/api/pair", body={"code": wrong})
        status, _ = self.request("POST", "/api/pair", body={"code": original})
        # O novo código poderia, por acaso, ser igual ao antigo (1 em 1 milhão).
        if self.server.pairing_code != original:
            self.assertEqual(status, 403)

    def test_malformed_pair_requests_are_rejected(self):
        for body in ("nada de json", json.dumps({"device": "x"}), json.dumps({"code": 123})):
            with self.subTest(body):
                status, _ = self.request("POST", "/api/pair", raw_body=body)
                self.assertEqual(status, 400)

    def test_oversized_pair_request_is_rejected(self):
        status, _ = self.request("POST", "/api/pair", raw_body="x" * (share.MAX_BODY_SIZE + 1))
        self.assertEqual(status, 400)

    def test_files_require_a_token(self):
        path, _ = self.make_file()
        shared = self.server.share(path)
        self.assertEqual(self.request("GET", "/api/files")[0], 401)
        self.assertEqual(self.request("GET", "/api/files", "token-falso")[0], 401)
        self.assertEqual(self.request("GET", f"/api/files/{shared.id}")[0], 401)
        self.assertEqual(self.request("GET", f"/api/files/{shared.id}", "token-falso")[0], 401)

    def test_download_returns_identical_bytes_and_updates_status(self):
        token = self.pair()
        path, content = self.make_file()
        shared = self.server.share(path)
        self.assertEqual(self.server.statuses(), [(path.name, share.STATUS_WAITING)])

        status, listing = self.request("GET", "/api/files", token)
        self.assertEqual(
            json.loads(listing)["files"], [{"id": shared.id, "name": "música.mp3", "size": len(content)}]
        )
        status, downloaded = self.request("GET", f"/api/files/{shared.id}", token)
        self.assertEqual((status, downloaded), (200, content))
        # O cliente pode terminar de ler um instante antes de o servidor atualizar a situação.
        deadline = time.monotonic() + 2
        while self.server.statuses()[0][1] != share.STATUS_SENT and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.server.statuses(), [(path.name, share.STATUS_SENT)])

    def test_only_shared_files_can_be_downloaded(self):
        token = self.pair()
        secret, _ = self.make_file("segredo.txt", b"privado")
        for attempt in ("nao-existe", str(secret), "..%2F..%2Fsegredo.txt", "../../segredo.txt"):
            with self.subTest(attempt):
                status, content = self.request("GET", f"/api/files/{attempt}", token)
                self.assertEqual(status, 404)
                self.assertNotIn(b"privado", content)

    def test_sharing_the_same_file_twice_keeps_one_entry(self):
        path, _ = self.make_file()
        self.assertEqual(self.server.share(path).id, self.server.share(path).id)
        self.assertEqual(len(self.server.statuses()), 1)

    def test_deleted_file_disappears_from_list(self):
        token = self.pair()
        path, _ = self.make_file()
        shared = self.server.share(path)
        path.unlink()
        self.assertEqual(json.loads(self.request("GET", "/api/files", token)[1])["files"], [])
        self.assertEqual(self.request("GET", f"/api/files/{shared.id}", token)[0], 404)

    def test_pairing_survives_a_restart_of_the_app(self):
        token = self.pair()
        server_id = self.server.store.server_id
        self.server.stop()
        self.server = self.start_server()
        self.assertEqual(self.server.store.server_id, server_id)
        self.assertEqual(self.request("GET", "/api/files", token)[0], 200)

    def test_token_is_not_stored_in_plain_text(self):
        token = self.pair()
        self.assertNotIn(token, self.store.read_text(encoding="utf-8"))

    def test_clients_outside_the_private_network_are_refused(self):
        with mock.patch.object(share, "_is_private", lambda _: False):
            self.assertEqual(self.request("GET", "/api/info")[0], 403)
            status, _ = self.request("POST", "/api/pair", body={"code": self.server.pairing_code})
            self.assertEqual(status, 403)

    def test_discovery_answers_only_the_right_request(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(2)
            client.sendto(b"outra coisa", ("127.0.0.1", self.udp_port))
            client.sendto(share.DISCOVERY_REQUEST, ("127.0.0.1", self.udp_port))
            reply = json.loads(client.recvfrom(1024)[0])
            self.assertEqual(reply["service"], "ytdown")
            self.assertEqual(reply["port"], self.server.port)
            self.assertEqual(reply["id"], self.server.store.server_id)
            client.settimeout(0.3)
            with self.assertRaises(TimeoutError):
                client.recvfrom(1024)

    def test_stop_interrupts_a_transfer_in_progress(self):
        token = self.pair()
        path, content = self.make_file(content=b"x" * (share.CHUNK_SIZE * 2000))
        shared = self.server.share(path)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("GET", f"/api/files/{shared.id}", headers={"Authorization": f"Bearer {token}"})
        response = connection.getresponse()
        response.read(share.CHUNK_SIZE)
        self.server.stop()
        with self.assertRaises((http.client.IncompleteRead, OSError)):
            response.read()

    def test_stop_also_cuts_connections_that_are_already_open(self):
        token = self.pair()
        connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        self.addCleanup(connection.close)
        headers = {"Authorization": f"Bearer {token}"}
        connection.request("GET", "/api/files", headers=headers)
        self.assertEqual(connection.getresponse().read(), b'{"files": []}')
        self.server.stop()
        # A mesma conexão (keep-alive) não pode continuar sendo atendida.
        with self.assertRaises((OSError, http.client.HTTPException)):
            connection.request("GET", "/api/files", headers=headers)
            connection.getresponse().read()

    def test_busy_port_gives_a_readable_error(self):
        other = share.ShareServer(store_path=self.store)
        with self.assertRaises(share.ShareError):
            other.start(http_port=self.server.port, discovery_port=self.udp_port)


class ThreadSafetyTests(unittest.TestCase):
    def test_on_change_runs_when_a_file_is_shared(self):
        with tempfile.TemporaryDirectory() as temp:
            called = threading.Event()
            server = share.ShareServer(on_change=called.set, store_path=Path(temp) / "p.json")
            server.share(Path(temp) / "a.mp3")
            self.assertTrue(called.is_set())


if __name__ == "__main__":
    unittest.main()
