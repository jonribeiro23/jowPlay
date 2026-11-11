"""Testa o servidor com conexões reais, usando apenas o próprio computador."""

import http.client
import hashlib
import json
import socket
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.fakes import FakeDevices
from ytdown.application.sharing import SharingSession
from ytdown.domain.errors import ShareError
from ytdown.domain.sharing import TransferStatus
from ytdown.infrastructure.sharing import server as server_module
from ytdown.infrastructure.sharing.server import CHUNK_SIZE, DISCOVERY_REQUEST, MAX_BODY_SIZE, LocalShareServer
from ytdown.infrastructure.sharing.device_store import JsonDeviceStore


class LocalShareServerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.devices = FakeDevices()
        self.server = self.start_server()

    def start_server(self, http_port=0, discovery_port=0):
        session = SharingSession(self.devices, failed_attempt_delay=0)
        server = LocalShareServer(session, name="pc-teste", http_port=http_port, discovery_port=discovery_port)
        server.start()
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

    def share_file(self, name="música.mp3", content=b"audio" * 50_000):
        path = self.dir / name
        path.write_bytes(content)
        return self.server.session.share(path), content

    def test_info_identifies_the_pc(self):
        status, content = self.request("GET", "/api/info")
        info = json.loads(content)
        self.assertEqual((status, info["service"], info["id"], info["port"]), (200, "ytdown", "pc-de-teste", self.server.port))

    def test_shared_identity_survives_store_and_session_recreation(self):
        path = self.dir / "track.mp3"
        path.write_bytes(b"audio")
        store_path = self.dir / "registry.json"
        first = SharingSession(JsonDeviceStore(store_path)).share(path)
        second = SharingSession(JsonDeviceStore(store_path)).share(path)
        self.assertEqual(first.id, second.id)
        self.assertNotIn(str(path), first.id)

    def test_pairing_gives_a_working_token(self):
        token = self.pair()
        self.assertEqual(self.request("GET", "/api/files", token), (200, b'{"files": []}'))
        self.assertEqual(self.devices.tokens[token], "Meu celular")

    def test_wrong_code_is_refused(self):
        wrong = "000000" if self.server.pairing_code != "000000" else "111111"
        status, content = self.request("POST", "/api/pair", body={"code": wrong})
        self.assertEqual(status, 403)
        self.assertNotIn(b"token", content)

    def test_malformed_pair_requests_are_rejected(self):
        for body in ("nada de json", json.dumps({"device": "x"}), json.dumps({"code": 123})):
            with self.subTest(body):
                self.assertEqual(self.request("POST", "/api/pair", raw_body=body)[0], 400)

    def test_oversized_pair_request_is_rejected(self):
        self.assertEqual(self.request("POST", "/api/pair", raw_body="x" * (MAX_BODY_SIZE + 1))[0], 400)

    def test_files_require_a_token(self):
        shared, _ = self.share_file()
        for path in ("/api/files", f"/api/files/{shared.id}"):
            for token in (None, "token-falso"):
                with self.subTest(path=path, token=token):
                    self.assertEqual(self.request("GET", path, token)[0], 401)

    def test_catalog_and_cover_require_authorization_and_reflect_changes(self):
        shared, _ = self.share_file()
        for path in ("/api/catalog", f"/api/covers/{shared.id}"):
            for token in (None, "token-falso"):
                self.assertEqual(self.request("GET", path, token)[0], 401)
        token = self.pair()
        info = mock.Mock(title="Título", artist="Artista")
        with mock.patch.object(server_module.MutagenMetadataReader, "read", return_value=info), \
             mock.patch.object(server_module.MutagenMetadataReader, "read_cover", return_value=b"cover one") as cover:
            status, body = self.request("GET", "/api/catalog", token)
            item = json.loads(body)["tracks"][0]
            self.assertEqual((status, item["id"], item["title"], item["artist"]), (200, shared.id, "Título", "Artista"))
            self.assertEqual(self.request("GET", f"/api/covers/{shared.id}", token), (200, b"cover one"))
            cover.return_value = b"cover two"
            updated = json.loads(self.request("GET", "/api/catalog", token)[1])["tracks"][0]
            self.assertNotEqual(item["revision"], updated["revision"])
            self.assertNotEqual(item["cover_revision"], updated["cover_revision"])
            cover.return_value = None
            self.assertIsNone(json.loads(self.request("GET", "/api/catalog", token)[1])["tracks"][0]["cover_revision"])
            self.assertEqual(self.request("GET", f"/api/covers/{shared.id}", token)[0], 404)
            self.assertEqual(self.request("GET", "/api/covers/desconhecido", token)[0], 404)

    def test_revision_detects_changed_content_even_with_same_size_and_timestamp(self):
        shared, _ = self.share_file(content=b"aaaa")
        token = self.pair()
        original_stat = shared.path.stat()
        first = json.loads(self.request("GET", "/api/catalog", token)[1])["tracks"][0]
        shared.path.write_bytes(b"bbbb")
        import os
        os.utime(shared.path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        second = json.loads(self.request("GET", "/api/catalog", token)[1])["tracks"][0]
        self.assertNotEqual(first["revision"], second["revision"])
        self.assertEqual(first["sha256"], hashlib.sha256(b"aaaa").hexdigest())
        self.assertEqual(second["sha256"], hashlib.sha256(b"bbbb").hexdigest())

    def test_download_returns_identical_bytes_and_updates_status(self):
        token = self.pair()
        shared, content = self.share_file()
        status, listing = self.request("GET", "/api/files", token)
        self.assertEqual(json.loads(listing)["files"], [{"id": shared.id, "name": "música.mp3", "size": len(content)}])
        self.assertEqual(self.request("GET", f"/api/files/{shared.id}", token), (200, content))
        # O cliente pode terminar de ler um instante antes de o servidor atualizar a situação.
        deadline = time.monotonic() + 2
        while self.server.statuses()[0][1] != TransferStatus.SENT and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.server.statuses(), [("música.mp3", TransferStatus.SENT)])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'precisa do ffmpeg')
    def test_five_tagged_tracks_download_with_metadata_and_cover(self):
        from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TRCK
        from ytdown.infrastructure.resources import asset
        cover = asset('default_cover.jpg').read_bytes()
        for i in range(5):
            path = self.dir / f'{i}.mp3'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=44100',
                            '-t', '0.1', str(path)], check=True)
            tags = ID3()
            tags.add(TIT2(encoding=3, text=f'Faixa {i}'))
            tags.add(TPE1(encoding=3, text='Artista'))
            tags.add(TALB(encoding=3, text='Álbum'))
            tags.add(TRCK(encoding=3, text=str(i + 1)))
            tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='', data=cover))
            tags.save(path)
            self.server.share(path)
        token = self.pair()
        status, listing = self.request('GET', '/api/files', token)
        files = json.loads(listing)['files']
        self.assertEqual((status, len(files)), (200, 5))
        for i, entry in enumerate(files):
            status, content = self.request('GET', f"/api/files/{entry['id']}", token)
            self.assertEqual(status, 200)
            downloaded = self.dir / f'download-{i}.mp3'
            downloaded.write_bytes(content)
            tags = ID3(downloaded)
            self.assertEqual((str(tags['TIT2']), str(tags['TPE1']), str(tags['TALB']), str(tags['TRCK'])),
                             (f'Faixa {i}', 'Artista', 'Álbum', str(i + 1)))
            self.assertEqual(tags.getall('APIC')[0].data, cover)

    def test_only_shared_files_can_be_downloaded(self):
        token = self.pair()
        secret = self.dir / "segredo.txt"
        secret.write_bytes(b"privado")
        for attempt in ("nao-existe", str(secret), "..%2F..%2Fsegredo.txt", "../../segredo.txt"):
            with self.subTest(attempt):
                status, content = self.request("GET", f"/api/files/{attempt}", token)
                self.assertEqual(status, 404)
                self.assertNotIn(b"privado", content)

    def test_deleted_file_cannot_be_downloaded(self):
        token = self.pair()
        shared, _ = self.share_file()
        shared.path.unlink()
        self.assertEqual(json.loads(self.request("GET", "/api/files", token)[1])["files"], [])
        self.assertEqual(self.request("GET", f"/api/files/{shared.id}", token)[0], 404)

    def test_clients_outside_the_private_network_are_refused(self):
        with mock.patch.object(server_module, "is_private", lambda _: False):
            self.assertEqual(self.request("GET", "/api/info")[0], 403)
            self.assertEqual(self.request("POST", "/api/pair", body={"code": self.server.pairing_code})[0], 403)

    def test_discovery_answers_only_the_right_request(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(2)
            address = ("127.0.0.1", self.server.discovery_port)
            client.sendto(b"outra coisa", address)
            client.sendto(DISCOVERY_REQUEST, address)
            reply = json.loads(client.recvfrom(1024)[0])
            self.assertEqual((reply["service"], reply["port"], reply["id"]), ("ytdown", self.server.port, "pc-de-teste"))
            client.settimeout(0.3)
            with self.assertRaises(TimeoutError):
                client.recvfrom(1024)

    def test_stop_interrupts_a_transfer_in_progress(self):
        token = self.pair()
        shared, _ = self.share_file(content=b"x" * (CHUNK_SIZE * 2000))
        connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("GET", f"/api/files/{shared.id}", headers={"Authorization": f"Bearer {token}"})
        response = connection.getresponse()
        response.read(CHUNK_SIZE)
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

    def test_start_does_not_do_a_slow_reverse_dns_lookup(self):
        def slow_lookup(*_):
            raise AssertionError("getfqdn não deveria ser chamado")

        with mock.patch.object(socket, "getfqdn", slow_lookup):
            self.start_server()

    def test_busy_port_gives_a_readable_error(self):
        other = LocalShareServer(
            SharingSession(self.devices), http_port=self.server.port, discovery_port=self.server.discovery_port
        )
        with self.assertRaises(ShareError):
            other.start()


if __name__ == "__main__":
    unittest.main()
