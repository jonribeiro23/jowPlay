"""Os arquivos da pasta gerenciada da biblioteca."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from ytdown.application.extraction import unique_path
from ytdown.domain.errors import LibraryError
from ytdown.infrastructure.windows_shell import send_to_recycle_bin

WINDOWS_MAX_PATH = 259  # 260 com o terminador nulo; caminhos longos não estão ativos por padrão.
COLLISION_ROOM = 5  # Espaço para " (99)" quando um nome já existe.


class FileSystemLibraryStorage:
    """Implementa LibraryStorage. Nenhuma operação sobrescreve um arquivo existente."""

    def __init__(self, root: Path, trash_file: Callable[[Path], None] = send_to_recycle_bin) -> None:
        self._root = root
        self._trash_file = trash_file

    @property
    def root(self) -> Path:
        return self._root

    def is_available(self) -> bool:
        """Não cria a raiz: a primeira extração continua responsável por isso."""
        try:
            return self._root.is_dir()
        except OSError:
            return False

    def absolute(self, rel_path: str) -> Path:
        """Recusa qualquer caminho que possa sair da biblioteca. No Windows, "C:/x" em
        joinpath troca de unidade e "..\\" sobe de pasta, então ":" e "\\" não são aceitos.
        """
        parts = PurePosixPath(rel_path).parts
        if (
            not parts
            or PurePosixPath(rel_path).is_absolute()
            or any(part in ("..", ".") or ":" in part or "\\" in part for part in parts)
        ):
            raise LibraryError(f"Caminho inválido na biblioteca: {rel_path}")
        path = self._root.joinpath(*parts)
        if not path.resolve().is_relative_to(self._root.resolve()):
            raise LibraryError(f"Caminho inválido na biblioteca: {rel_path}")
        return path

    def exists(self, rel_path: str) -> bool:
        return self.absolute(rel_path).is_file()

    def max_relative_length(self) -> int:
        return WINDOWS_MAX_PATH - len(str(self._root)) - 1 - COLLISION_ROOM

    def place(self, source: Path, rel_path: str) -> str:
        try:
            return self._move_into_place(source, self.absolute(rel_path))
        except OSError as exc:
            raise LibraryError(f"Não foi possível salvar {rel_path} na biblioteca: {exc}") from exc

    def move(self, rel_path: str, new_rel_path: str) -> str:
        source = self.absolute(rel_path)
        target = self.absolute(new_rel_path)
        if str(source) == str(target):  # Path("a") == Path("A") no Windows; aqui a grafia importa.
            return rel_path
        try:
            if os.path.normcase(source) == os.path.normcase(target):
                final = self._rename_case_only(source, target)  # O Windows não diferencia maiúsculas.
            else:
                final = self._move_into_place(source, target)
        except OSError as exc:
            raise LibraryError(f"Não foi possível mover {rel_path} para {new_rel_path}: {exc}") from exc
        self._remove_empty_folders(source.parent)
        return final

    def trash(self, rel_path: str) -> None:
        path = self.absolute(rel_path)
        try:
            self._trash_file(path)
        except OSError as exc:
            raise LibraryError(f"Não foi possível enviar {rel_path} para a Lixeira: {exc}") from exc
        self._remove_empty_folders(path.parent)

    def discard(self, rel_path: str) -> None:
        path = self.absolute(rel_path)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise LibraryError(f"Não foi possível apagar {rel_path} da biblioteca: {exc}") from exc
        self._remove_empty_folders(path.parent)

    def relocate(self, new_root: Path, on_progress: Callable[[int, int], None]) -> dict[str, str]:
        old_root = self._root
        if os.path.normcase(new_root.resolve()) == os.path.normcase(old_root.resolve()):
            return {}
        if new_root.resolve().is_relative_to(old_root.resolve()) or old_root.resolve().is_relative_to(new_root.resolve()):
            raise LibraryError("A nova pasta da biblioteca não pode ficar dentro da atual, nem conter a atual.")

        files = sorted(p for p in old_root.rglob("*") if p.is_file()) if old_root.exists() else []
        moved: list[tuple[Path, Path]] = []
        renamed: dict[str, str] = {}
        try:
            for done, source in enumerate(files, start=1):
                rel = source.relative_to(old_root).as_posix()
                target = unique_path(new_root / source.relative_to(old_root))
                target.parent.mkdir(parents=True, exist_ok=True)
                _safe_move(source, target)
                moved.append((source, target))
                if target != new_root / source.relative_to(old_root):
                    renamed[rel] = target.relative_to(new_root).as_posix()
                on_progress(done, len(files))
        except OSError as exc:
            self._undo_moves(moved)
            raise LibraryError(f"Não foi possível mover a biblioteca para {new_root}: {exc}") from exc

        for source, _ in moved:
            self._remove_empty_folders(source.parent, stop_at=old_root)
        self._root = new_root
        return renamed

    # --- detalhes

    def _move_into_place(self, source: Path, target: Path) -> str:
        target.parent.mkdir(parents=True, exist_ok=True)
        final = unique_path(target)
        _safe_move(source, final)
        return final.relative_to(self._root).as_posix()

    def _rename_case_only(self, source: Path, target: Path) -> str:
        temporary = unique_path(source.with_name(source.name + ".ytdown-tmp"))
        source.rename(temporary)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.rename(target)
        return target.relative_to(self._root).as_posix()

    def _remove_empty_folders(self, folder: Path, stop_at: Path | None = None) -> None:
        """Apaga as pastas vazias de `folder` para cima, sem nunca apagar a raiz."""
        stop_at = stop_at or self._root
        while folder != stop_at and folder.is_relative_to(stop_at):
            try:
                folder.rmdir()  # Só funciona se a pasta estiver vazia.
            except OSError:
                return
            folder = folder.parent

    @staticmethod
    def _undo_moves(moved: list[tuple[Path, Path]]) -> None:
        for source, target in reversed(moved):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                _safe_move(target, source)
            except OSError:
                pass  # Melhor esforço: o erro original já será informado.


def _safe_move(source: Path, target: Path) -> None:
    """Move `source` para `target`, que ainda não existe.

    Entre unidades diferentes, ou se o rename falhar, o shutil copia e depois apaga a
    origem. Se apagar a origem falhar (arquivo em uso), a cópia é desfeita para não
    deixar o mesmo arquivo em dois lugares.
    """
    try:
        shutil.move(source, target)
    except OSError:
        if source.exists() and target.exists():
            target.unlink(missing_ok=True)
        raise
