"""Regras do compartilhamento: quais áudios estão disponíveis, a situação de cada
um e o pareamento do celular. Não sabe nada de rede; o servidor usa esta sessão.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ytdown.application.ports import DeviceRegistry
from ytdown.domain.sharing import SharedFile, TransferStatus

MAX_FAILED_ATTEMPTS = 5  # Depois disso, o código muda.
FAILED_ATTEMPT_DELAY = 1.0  # Segundos; torna inviável testar todos os códigos.


class SharedLibraryResolver(Protocol):
    def identify(self, path: Path) -> str | None: ...
    def resolve(self, share_id: str) -> Path | None: ...


def new_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class SharingSession:
    """Seguro para uso em várias threads. `on_change` é chamado quando algo visível muda."""

    def __init__(
        self,
        devices: DeviceRegistry,
        on_change: Callable[[], None] = lambda: None,
        failed_attempt_delay: float = FAILED_ATTEMPT_DELAY,
        library: SharedLibraryResolver | None = None,
    ) -> None:
        self.devices = devices
        self._library = library
        self._on_change = on_change
        self._failed_attempt_delay = failed_attempt_delay
        self._lock = threading.Lock()
        self._pair_lock = threading.Lock()
        self._pairing_code = new_pairing_code()
        self._failed_attempts = 0
        self._files: dict[str, SharedFile] = {}
        self._status: dict[str, TransferStatus] = {}
        self._library_ids: set[str] = set()

    @property
    def pairing_code(self) -> str:
        return self._pairing_code

    # --- arquivos

    def share(self, path: Path) -> SharedFile:
        library_id = self._library.identify(path) if self._library else None
        with self._lock:
            for shared in list(self._files.values()):
                if shared.id == library_id:
                    self._library_ids.add(shared.id)
                    return shared
                if shared.path == path and shared.id not in self._library_ids:
                    if library_id is None:
                        return shared
                    del self._files[shared.id]
                    del self._status[shared.id]
            identify = getattr(self.devices, "shared_id", None)
            shared = SharedFile(library_id or (identify(path) if identify else secrets.token_urlsafe(16)), path)
            self._files[shared.id] = shared
            if library_id:
                self._library_ids.add(shared.id)
            self._status[shared.id] = TransferStatus.WAITING
        self._on_change()
        return shared

    def get(self, file_id: str) -> SharedFile | None:
        with self._lock:
            shared = self._files.get(file_id)
            library_file = file_id in self._library_ids
        if shared and library_file:
            path = self._library.resolve(file_id)
            return SharedFile(file_id, path) if path else None
        return shared

    def available(self) -> list[tuple[SharedFile, int]]:
        """Arquivos que ainda existem, com o tamanho em bytes."""
        with self._lock:
            ids = list(self._files)
        result = []
        for file_id in ids:
            shared = self.get(file_id)
            if shared is None:
                continue
            try:
                result.append((shared, shared.path.stat().st_size))
            except OSError:
                pass  # O usuário apagou ou moveu o arquivo.
        return result

    def statuses(self) -> list[tuple[str, TransferStatus]]:
        with self._lock:
            entries = [(shared, self._status[shared.id]) for shared in self._files.values()]
        return [((self.get(shared.id) or shared).name, status) for shared, status in entries]

    def set_status(self, file_id: str, status: TransferStatus) -> None:
        with self._lock:
            self._status[file_id] = status
        self._on_change()

    # --- pareamento

    def is_authorized(self, token: str) -> bool:
        return bool(token) and self.devices.knows(token)

    def try_pair(self, code: str, device_name: str) -> str | None:
        """Devolve um token se o código estiver certo. O código muda após cada uso."""
        # O lock faz as tentativas erradas acontecerem uma de cada vez, com espera.
        with self._pair_lock:
            if secrets.compare_digest(code.encode(), self._pairing_code.encode()):
                self._renew_code()
                token = self.devices.add_device(device_name)
                self._on_change()
                return token
            time.sleep(self._failed_attempt_delay)
            self._failed_attempts += 1
            if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
                self._renew_code()
                self._on_change()
            return None

    def _renew_code(self) -> None:
        self._pairing_code = new_pairing_code()
        self._failed_attempts = 0
