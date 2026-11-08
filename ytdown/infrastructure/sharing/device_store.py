"""Celulares pareados, guardados em um arquivo JSON. Os tokens são salvos como hash."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
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
        data = self._load()
        self._server_id: str = data.get("server_id") or secrets.token_hex(8)
        self._devices: dict[str, str] = data.get("devices", {})  # hash do token -> nome
        if "server_id" not in data:
            self._save()

    @property
    def server_id(self) -> str:
        return self._server_id

    def add_device(self, name: str) -> str:
        token = secrets.token_urlsafe(32)
        self._devices[_hash_token(token)] = name
        self._save()
        return token

    def knows(self, token: str) -> bool:
        return _hash_token(token) in self._devices

    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"server_id": self._server_id, "devices": self._devices}, ensure_ascii=False)
        self._path.write_text(content, encoding="utf-8")
