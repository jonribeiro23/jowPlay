"""Servidor da rede local que entrega ao celular os áudios da SharingSession.

Decisões de segurança:
- Só existem para download os arquivos compartilhados na sessão; o celular pede
  por um identificador aleatório e nunca informa um caminho do computador.
- O celular precisa de um token, obtido uma vez com o código exibido no PC.
- Conexões de fora da rede privada são recusadas.
- O tráfego não é criptografado: use apenas em redes de confiança.
"""

from __future__ import annotations

import ipaddress
import hashlib
import json
import os
import socket
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ytdown.application.sharing import SharingSession
from ytdown.domain.errors import ShareError
from ytdown.domain.errors import UnreadableAudio
from ytdown.domain.sharing import TransferStatus
from ytdown.infrastructure.metadata_reader import MutagenMetadataReader

DISCOVERY_PORT = 47820
HTTP_PORT = 47821
DISCOVERY_REQUEST = b"YTDOWN_DISCOVER_V1"
PROTOCOL_VERSION = 1
MAX_BODY_SIZE = 1024
CHUNK_SIZE = 64 * 1024


def is_private(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_private
    except ValueError:
        return False


def local_address() -> str:
    """Endereço deste PC na rede. Conectar um socket UDP não envia nenhum pacote."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
            return probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 30  # Uma conexão parada não pode prender uma thread para sempre.
    server: "_HttpServer"

    @property
    def _owner(self) -> "LocalShareServer":
        return self.server.owner

    @property
    def _session(self) -> SharingSession:
        return self.server.owner.session

    def setup(self) -> None:
        super().setup()
        self._owner._track(self.connection)

    def finish(self) -> None:
        try:
            super().finish()
        finally:
            self._owner._untrack(self.connection)

    def log_message(self, format: str, *args) -> None:
        pass  # Um app com janela não tem console (sys.stderr é None).

    # --- rotas

    def do_GET(self) -> None:
        if not self._allowed_client():
            return
        if self.path == "/api/info":
            self._send_json(200, self._owner.info())
        elif self.path == "/api/files":
            if self._authorized():
                files = [
                    {"id": shared.id, "name": shared.name, "size": size}
                    for shared, size in self._session.available()
                ]
                self._send_json(200, {"files": files})
        elif self.path == "/api/catalog":
            if self._authorized():
                items = (self._catalog_item(shared, size) for shared, size in self._session.available())
                self._send_json(200, {"tracks": [item for item in items if item is not None]})
        elif self.path.startswith("/api/covers/"):
            if self._authorized():
                self._send_cover(self.path.removeprefix("/api/covers/"))
        elif self.path.startswith("/api/files/"):
            if self._authorized():
                self._send_file(self.path.removeprefix("/api/files/"))
        else:
            self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if not self._allowed_client():
            return
        if self.path != "/api/pair":
            self._reject(404, "not_found")
            return
        request = self._read_pair_request()
        if request is None:
            self._reject(400, "bad_request")
            return
        code, device = request
        token = self._session.try_pair(code, device)
        if token is None:
            self._send_json(403, {"error": "wrong_code"})
        else:
            self._send_json(200, {"token": token, **self._owner.info()})

    # --- etapas

    def _metadata(self, shared):
        try:
            reader = MutagenMetadataReader()
            return reader.read(shared.path), reader.read_cover(shared.path)
        except UnreadableAudio:
            return None, None

    def _catalog_item(self, shared, size):
        info, cover = self._metadata(shared)
        title = (info.title if info else None) or shared.path.stem
        artist = (info.artist if info else None) or ""
        try:
            with shared.path.open("rb") as source:
                before = os.fstat(source.fileno())
                digest = hashlib.sha256()
                while chunk := source.read(CHUNK_SIZE):
                    digest.update(chunk)
                after = os.fstat(source.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                return None
        except OSError:
            return None
        size = after.st_size
        revision = hashlib.sha256(json.dumps([shared.name, title, artist, size, digest.hexdigest(),
            hashlib.sha256(cover).hexdigest() if cover else None], ensure_ascii=False).encode()).hexdigest()
        return {"id": shared.id, "name": shared.name, "size": size, "title": title,
                "artist": artist, "cover_revision": hashlib.sha256(cover).hexdigest() if cover else None,
                "revision": revision, "sha256": digest.hexdigest()}

    def _send_cover(self, file_id):
        shared = self._session.get(file_id)
        _, cover = self._metadata(shared) if shared else (None, None)
        if not cover:
            self._send_json(404, {"error": "not_found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(cover)))
        self.end_headers()
        self.wfile.write(cover)

    def _allowed_client(self) -> bool:
        if self._owner.stopping:
            self._reject(503, "stopped")
            return False
        if not is_private(self.client_address[0]):
            self._reject(403, "forbidden")
            return False
        return True

    def _authorized(self) -> bool:
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme == "Bearer" and self._session.is_authorized(token.strip()):
            return True
        self._send_json(401, {"error": "not_paired"})
        return False

    def _read_pair_request(self) -> tuple[str, str] | None:
        try:
            length = int(self.headers.get("Content-Length", ""))
            if not 0 < length <= MAX_BODY_SIZE:
                return None
            body = json.loads(self.rfile.read(length))
            code = body["code"]
            device = str(body.get("device", ""))[:80] or "Celular"
        except (ValueError, KeyError, TypeError):
            return None
        return (code, device) if isinstance(code, str) else None

    def _send_file(self, file_id: str) -> None:
        shared = self._session.get(file_id)
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
            self._session.set_status(file_id, TransferStatus.SENDING)
            sent = self._copy_to_client(source)
        if sent == size:
            self._session.set_status(file_id, TransferStatus.SENT)
        else:
            self.close_connection = True
            self._session.set_status(file_id, TransferStatus.FAILED)

    def _copy_to_client(self, source) -> int:
        sent = 0
        try:
            while chunk := source.read(CHUNK_SIZE):
                if self._owner.stopping:
                    break
                self.wfile.write(chunk)
                sent += len(chunk)
            self.wfile.flush()
        except OSError:  # O celular desconectou ou a conexão expirou.
            pass
        return sent

    def _reject(self, status: int, error: str) -> None:
        self.close_connection = True
        self._send_json(status, {"error": error})

    def _send_json(self, status: int, body: dict) -> None:
        content = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


class _HttpServer(ThreadingHTTPServer):
    daemon_threads = True
    owner: "LocalShareServer"

    def handle_error(self, request, client_address) -> None:
        pass  # Conexões interrompidas são normais; sys.stderr é None no app com janela.

    def server_bind(self) -> None:
        # O HTTPServer padrão faz aqui uma consulta de DNS reversa (socket.getfqdn) cujo
        # resultado nunca é usado; ela travava a janela por cerca de 1 s ou mais.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class LocalShareServer:
    """Implementa ShareServer: HTTP para os arquivos e UDP para o celular encontrar o PC.

    Funciona apenas entre start() e stop().
    """

    def __init__(
        self,
        session: SharingSession,
        name: str | None = None,
        http_port: int = HTTP_PORT,
        discovery_port: int = DISCOVERY_PORT,
    ) -> None:
        self.session = session
        self.name = name or socket.gethostname()
        self.stopping = False
        self._http_port = http_port
        self._discovery_port = discovery_port
        self._http: _HttpServer | None = None
        self._udp: socket.socket | None = None
        self._threads: list[threading.Thread] = []
        self._connections: set[socket.socket] = set()
        self._connections_lock = threading.Lock()

    # --- ShareServer

    @property
    def port(self) -> int:
        return self._http.server_address[1]

    @property
    def discovery_port(self) -> int:
        return self._udp.getsockname()[1]

    @property
    def pairing_code(self) -> str:
        return self.session.pairing_code

    def start(self) -> None:
        try:
            self._http = _HttpServer(("0.0.0.0", self._http_port), _Handler)
            self._http.owner = self
            self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp.bind(("0.0.0.0", self._discovery_port))
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
        self._close_open_connections()
        for thread in self._threads:
            thread.join(timeout=2)
        if self._udp:
            self._udp.close()

    def address(self) -> str:
        return f"{local_address()}:{self.port}"

    def share(self, path: Path) -> None:
        self.session.share(path)

    def statuses(self) -> list[tuple[str, TransferStatus]]:
        return self.session.statuses()

    # --- detalhes

    def info(self) -> dict:
        return {
            "service": "ytdown",
            "version": PROTOCOL_VERSION,
            "id": self.session.devices.server_id,
            "name": self.name,
            "port": self.port,
        }

    def _close_open_connections(self) -> None:
        # O celular mantém a conexão aberta entre pedidos (keep-alive); sem isto,
        # ele continuaria vendo a lista mesmo depois de "Parar de compartilhar".
        with self._connections_lock:
            connections = list(self._connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # Já estava fechada.

    def _track(self, connection: socket.socket) -> None:
        with self._connections_lock:
            self._connections.add(connection)
        if self.stopping:  # Chegou durante o encerramento.
            connection.shutdown(socket.SHUT_RDWR)

    def _untrack(self, connection: socket.socket) -> None:
        with self._connections_lock:
            self._connections.discard(connection)

    def _answer_discovery(self) -> None:
        while not self.stopping:
            try:
                data, sender = self._udp.recvfrom(64)
                if data == DISCOVERY_REQUEST and is_private(sender[0]):
                    self._udp.sendto(json.dumps(self.info()).encode(), sender)
            except TimeoutError:
                continue
            except OSError:
                if self.stopping:
                    return
                # No Windows, um destino que sumiu gera erro aqui; o servidor deve continuar.
