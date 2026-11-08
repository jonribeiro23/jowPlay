"""Casos de uso da biblioteca."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from ytdown.application.ports import LibraryStorage, Settings, TrackRepository

LIBRARY_FOLDER_KEY = "library_folder"


def library_folder(settings: Settings, default: Path) -> Path:
    """A pasta da biblioteca escolhida pelo usuário, ou `default` se ele nunca escolheu."""
    chosen = settings.get(LIBRARY_FOLDER_KEY)
    return Path(chosen) if chosen else default


class ChangeLibraryFolder:
    """Move a biblioteca inteira para outra pasta, mantendo o índice coerente."""

    def __init__(self, storage: LibraryStorage, tracks: TrackRepository, settings: Settings) -> None:
        self._storage = storage
        self._tracks = tracks
        self._settings = settings

    def __call__(self, new_root: Path, on_progress: Callable[[int, int], None] = lambda done, total: None) -> None:
        """Falha com LibraryError; nesse caso, nada muda (nem arquivos, nem índice, nem configuração)."""
        renamed = self._storage.relocate(new_root, on_progress)
        # Só arquivos que colidiram com algo já existente na pasta nova mudam de nome.
        for old_path, new_path in renamed.items():
            track = self._tracks.find_by_path(old_path)
            if track:
                self._tracks.update(replace(track, rel_path=new_path))
        self._settings.set(LIBRARY_FOLDER_KEY, str(new_root))
