"""Servidor da rede local que entrega ao celular os áudios escolhidos pelo usuário.

Decisões de segurança:
- Só existem para download os arquivos passados a `share()`; o celular pede por
  um identificador aleatório e nunca informa um caminho do computador.
- O celular precisa de um token, obtido uma vez com o código exibido no PC.
- Conexões de fora da rede privada são recusadas.
- O tráfego não é criptografado: use apenas em redes de confiança.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import secrets
import socket
import socketserver
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DISCOVERY_PORT = 47820
HTTP_PORT = 47821
DISCOVERY_REQUEST = b"YTDOWN_DISCOVER_V1"
MAX_PAIR_ATTEMPTS = 5  # Depois disso, o código muda.
FAILED_PAIR_DELAY = 1.0  # Segundos; torna inviável testar todos os códigos.
MAX_BODY_SIZE = 1024
CHUNK_SIZE = 64 * 1024

STATUS_WAITING = "Aguardando o celular"
STATUS_SENDING = "Enviando..."
STATUS_SENT = "Enviado"
STATUS_FAILED = "Falhou; o celular pode tentar de novo"


def default_store_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ytDown" / "pairing.json"


class ShareError(Exception):
    """Falha com uma mensagem pronta para ser mostrada ao usuário."""


@dataclass(frozen=True)
class SharedFile:
    id: str
    path: Path
    name: str


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _is_private(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_private
    except ValueError:
        return False


class _PairingStore:
    """Guarda a identidade do PC e os celulares pareados. Tokens são salvos como hash."""

    def __init__(self, path: Path) -> None:
        self.path = path
        data = self._load()
        self.server_id: str = data.get("server_id") or secrets.token_hex(8)
        self.devices: dict[str, str] = data.get("devices", {})  # hash do token -> nome
        if "server_id" not in data:
            self._save()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"server_id": self.server_id, "devices": self.devices}, ensure_ascii=False)
        self.path.write_text(content, encoding="utf-8")

    def add_device(self, name: str) -> str:
        token = secrets.token_urlsafe(32)
        self.devices[_hash_token(token)] = name
        self._save()
        return token

    def device_for(self, token: str) -> str | None:
        return self.devices.get(_hash_token(token))


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 30  # Uma conexão parada não pode prender uma thread para sempre.
    server: "_HttpServer"

    def setup(self) -> None:
        super().setup()
        self.server.owner._track(self.connection)

    def finish(self) -> None:
        try:
            super().finish()
        finally:
            self.server.owner._untrack(self.connection)

    def log_message(self, format: str, *args) -> None:
        pass  # Um app com janela não tem console (sys.stderr é None).

    def _send_json(self, status: int, body: dict) -> None:
        content = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _authorized(self) -> bool:
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme == "Bearer" and self.server.owner.store.device_for(token.strip()) is not None:
            return True
        self._send_json(401, {"error": "not_paired"})
        return False

    def _allowed_client(self) -> bool:
        if self.server.owner.stopping:
            self.close_connection = True
            self._send_json(503, {"error": "stopped"})
            return False
        if _is_private(self.client_address[0]):
            return True
        self.close_connection = True
        self._send_json(403, {"error": "forbidden"})
        return False

    def do_GET(self) -> None:
        if not self._allowed_client():
            return
        owner = self.server.owner
        if self.path == "/api/info":
            self._send_json(200, owner.info())
        elif self.path == "/api/files":
            if self._authorized():
                self._send_json(200, {"files": owner.list_files()})
        elif self.path.startswith("/api/files/"):
            if self._authorized():
                self._send_file(self.path.removeprefix("/api/files/"))
        else:
            self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if not self._allowed_client():
            return
        if self.path != "/api/pair":
            self.close_connection = True
            self._send_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            if not 0 < length <= MAX_BODY_SIZE:
                raise ValueError
            body = json.loads(self.rfile.read(length))
            code = body["code"]
            device = str(body.get("device", ""))[:80] or "Celular"
            if not isinstance(code, str):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            self.close_connection = True
            self._send_json(400, {"error": "bad_request"})
            return

        token = self.server.owner.try_pair(code, device)
        if token is None:
            self._send_json(403, {"error": "wrong_code"})
        else:
            self._send_json(200, {"token": token, **self.server.owner.info()})

    def _send_file(self, file_id: str) -> None:
        owner = self.server.owner
        shared = owner.get_file(file_id)
        try:
            source = shared.path.open("rb") if shared else None
        except OSError:
            source = None
        if source is None:
            self._send_json(404, {"error": "not_found"})
            return

        with source:
            size = os.fstat(source.fileno()).st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            owner.set_status(file_id, STATUS_SENDING)
            sent = 0
            try:
                while chunk := source.read(CHUNK_SIZE):
                    if owner.stopping:
                        break
                    self.wfile.write(chunk)
                    sent += len(chunk)
                self.wfile.flush()
            except OSError:  # O celular desconectou ou a conexão expirou.
                pass
        if sent == size:
            owner.set_status(file_id, STATUS_SENT)
        else:
            self.close_connection = True
            owner.set_status(file_id, STATUS_FAILED)


class _HttpServer(ThreadingHTTPServer):
    daemon_threads = True
    owner: "ShareServer"

    def handle_error(self, request, client_address) -> None:
        pass  # Conexões interrompidas são normais; sys.stderr é None no app com janela.

    def server_bind(self) -> None:
        # O HTTPServer padrão faz aqui uma consulta de DNS reversa (socket.getfqdn) cujo
        # resultado nunca é usado; ela travava a janela por cerca de 1 s ou mais.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class ShareServer:
    """Roda apenas entre start() e stop(). `on_change` é chamado em outras threads."""

    def __init__(self, on_change: Callable[[], None] = lambda: None, store_path: Path | None = None) -> None:
        self.on_change = on_change
        self.store = _PairingStore(store_path or default_store_path())
        self.name = socket.gethostname()
        self.pairing_code = _new_code()
        self.stopping = False
        self._lock = threading.Lock()
        self._pair_lock = threading.Lock()
        self._failed_attempts = 0
        self._files: dict[str, SharedFile] = {}
        self._status: dict[str, str] = {}
        self._connections: set[socket.socket] = set()
        self._http: _HttpServer | None = None
        self._udp: socket.socket | None = None
        self._threads: list[threading.Thread] = []

    @property
    def port(self) -> int:
        return self._http.server_address[1]

    def start(self, http_port: int = HTTP_PORT, discovery_port: int = DISCOVERY_PORT) -> None:
        try:
            self._http = _HttpServer(("0.0.0.0", http_port), _Handler)
            self._http.owner = self
            self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp.bind(("0.0.0.0", discovery_port))
            self._udp.settimeout(0.5)
        except OSError as exc:
            self.stop()
            raise ShareError(
                "Não foi possível iniciar o compartilhamento. "
                f"Verifique se o ytDown já está aberto em outra janela. ({exc})"
            ) from exc
        for target in (self._http.serve_forever, self._answer_discovery):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self.stopping = True
        if self._http:
            if self._threads:
                self._http.shutdown()
            self._http.server_close()
        # O celular mantém a conexão aberta entre pedidos (keep-alive); sem isto,
        # ele continuaria vendo a lista mesmo depois de "Parar de compartilhar".
        with self._lock:
            connections = list(self._connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # Já estava fechada.
        for thread in self._threads:
            thread.join(timeout=2)
        if self._udp:
            self._udp.close()

    def _track(self, connection: socket.socket) -> None:
        with self._lock:
            self._connections.add(connection)
        if self.stopping:  # Chegou durante o encerramento.
            connection.shutdown(socket.SHUT_RDWR)

    def _untrack(self, connection: socket.socket) -> None:
        with self._lock:
            self._connections.discard(connection)

    def share(self, path: Path) -> SharedFile:
        with self._lock:
            for shared in self._files.values():
                if shared.path == path:
                    return shared
            shared = SharedFile(secrets.token_urlsafe(16), path, path.name)
            self._files[shared.id] = shared
            self._status[shared.id] = STATUS_WAITING
        self.on_change()
        return shared

    def info(self) -> dict:
        return {"service": "ytdown", "version": 1, "id": self.store.server_id, "name": self.name, "port": self.port}

    def list_files(self) -> list[dict]:
        with self._lock:
            files = list(self._files.values())
        result = []
        for shared in files:
            try:
                result.append({"id": shared.id, "name": shared.name, "size": shared.path.stat().st_size})
            except OSError:
                pass  # O usuário apagou ou moveu o arquivo.
        return result

    def get_file(self, file_id: str) -> SharedFile | None:
        with self._lock:
            return self._files.get(file_id)

    def statuses(self) -> list[tuple[str, str]]:
        with self._lock:
            return [(shared.name, self._status[shared.id]) for shared in self._files.values()]

    def set_status(self, file_id: str, status: str) -> None:
        with self._lock:
            self._status[file_id] = status
        self.on_change()

    def try_pair(self, code: str, device: str) -> str | None:
        # O lock faz as tentativas erradas acontecerem uma de cada vez, com espera.
        with self._pair_lock:
            if secrets.compare_digest(code.encode(), self.pairing_code.encode()):
                self.pairing_code = _new_code()
                self._failed_attempts = 0
                token = self.store.add_device(device)
                self.on_change()
                return token
            time.sleep(FAILED_PAIR_DELAY)
            self._failed_attempts += 1
            if self._failed_attempts >= MAX_PAIR_ATTEMPTS:
                self.pairing_code = _new_code()
                self._failed_attempts = 0
                self.on_change()
            return None

    def _answer_discovery(self) -> None:
        while not self.stopping:
            try:
                data, sender = self._udp.recvfrom(64)
                if data == DISCOVERY_REQUEST and _is_private(sender[0]):
                    self._udp.sendto(json.dumps(self.info()).encode(), sender)
            except TimeoutError:
                continue
            except OSError:
                if self.stopping:
                    return
                # No Windows, um destino que sumiu gera erro aqui; o servidor deve continuar.


def local_address() -> str:
    """Endereço deste PC na rede. Conectar um socket UDP não envia nenhum pacote."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
            return probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"
