"""Regras do compartilhamento: quais áudios estão disponíveis, a situação de cada
um e o pareamento do celular. Não sabe nada de rede; o servidor usa esta sessão.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path

from ytdown.application.ports import DeviceRegistry
from ytdown.domain.sharing import SharedFile, TransferStatus

MAX_FAILED_ATTEMPTS = 5  # Depois disso, o código muda.
FAILED_ATTEMPT_DELAY = 1.0  # Segundos; torna inviável testar todos os códigos.


def new_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class SharingSession:
    """Seguro para uso em várias threads. `on_change` é chamado quando algo visível muda."""

    def __init__(
        self,
        devices: DeviceRegistry,
        on_change: Callable[[], None] = lambda: None,
        failed_attempt_delay: float = FAILED_ATTEMPT_DELAY,
    ) -> None:
        self.devices = devices
        self._on_change = on_change
        self._failed_attempt_delay = failed_attempt_delay
        self._lock = threading.Lock()
        self._pair_lock = threading.Lock()
        self._pairing_code = new_pairing_code()
        self._failed_attempts = 0
        self._files: dict[str, SharedFile] = {}
        self._status: dict[str, TransferStatus] = {}

    @property
    def pairing_code(self) -> str:
        return self._pairing_code

    # --- arquivos

    def share(self, path: Path) -> SharedFile:
        with self._lock:
            for shared in self._files.values():
                if shared.path == path:
                    return shared
            shared = SharedFile(secrets.token_urlsafe(16), path)
            self._files[shared.id] = shared
            self._status[shared.id] = TransferStatus.WAITING
        self._on_change()
        return shared

    def get(self, file_id: str) -> SharedFile | None:
        with self._lock:
            return self._files.get(file_id)

    def available(self) -> list[tuple[SharedFile, int]]:
        """Arquivos que ainda existem, com o tamanho em bytes."""
        with self._lock:
            files = list(self._files.values())
        result = []
        for shared in files:
            try:
                result.append((shared, shared.path.stat().st_size))
            except OSError:
                pass  # O usuário apagou ou moveu o arquivo.
        return result

    def statuses(self) -> list[tuple[str, TransferStatus]]:
        with self._lock:
            return [(shared.name, self._status[shared.id]) for shared in self._files.values()]

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
