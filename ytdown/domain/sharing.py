"""Conceitos do compartilhamento de áudios com o celular."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


class TransferStatus(Enum):
    WAITING = auto()
    SENDING = auto()
    SENT = auto()
    FAILED = auto()


@dataclass(frozen=True)
class SharedFile:
    """Um áudio oferecido ao celular. O celular só conhece o `id`, nunca o caminho."""

    id: str
    path: Path

    @property
    def name(self) -> str:
        return self.path.name
