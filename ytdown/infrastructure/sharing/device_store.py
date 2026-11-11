"""Celulares pareados, guardados em um arquivo JSON. Os tokens são salvos como hash."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from pathlib import Path


def default_store_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ytDown" / "pairing.json"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class JsonDeviceStore:
    """Implementa DeviceRegistry."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        data = self._load()
        self._server_id: str = data.get("server_id") or secrets.token_hex(8)
        self._devices: dict[str, str] = data.get("devices", {})  # hash do token -> nome
        self._shared_ids: dict[str, str] = data.get("shared_ids", {})
        if "server_id" not in data:
            self._save()

    @property
    def server_id(self) -> str:
        return self._server_id

    def add_device(self, name: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._devices[_hash_token(token)] = name
            self._save()
        return token

    def knows(self, token: str) -> bool:
        with self._lock:
            return _hash_token(token) in self._devices

    def shared_id(self, path: Path) -> str:
        """Preserva a identidade do caminho entre sessões do servidor."""
        key = os.path.normcase(os.path.abspath(path))
        with self._lock:
            if key not in self._shared_ids:
                self._shared_ids[key] = secrets.token_urlsafe(16)
                self._save()
            return self._shared_ids[key]

    def existing_shared_id(self, path: Path) -> str | None:
        with self._lock:
            return self._shared_ids.get(os.path.normcase(os.path.abspath(path)))

    def forget_shared_id(self, path: Path) -> None:
        key = os.path.normcase(os.path.abspath(path))
        with self._lock:
            if key in self._shared_ids:
                del self._shared_ids[key]
                self._save()

    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"server_id": self._server_id, "devices": self._devices,
                              "shared_ids": self._shared_ids}, ensure_ascii=False)
        self._path.write_text(content, encoding="utf-8")
