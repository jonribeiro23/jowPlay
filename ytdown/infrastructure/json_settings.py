"""Preferências do app em um arquivo JSON."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def default_settings_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ytDown" / "settings.json"


class JsonSettings:
    """Implementa Settings.

    Cada alteração regrava o arquivo inteiro de forma atômica (arquivo temporário +
    troca), então uma queda no meio nunca deixa o arquivo pela metade. Um arquivo
    ilegível é ignorado: o app abre com os valores padrão.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._values = self._load()

    def get(self, key: str, default=None):
        return self._values.get(key, default)

    def set(self, key: str, value) -> None:
        self._values[key] = value
        self._save()

    def _load(self) -> dict:
        try:
            values = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return values if isinstance(values, dict) else {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=self._path.parent, prefix=".settings-", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(self._values, file, ensure_ascii=False, indent=2)
            os.replace(temporary, self._path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
