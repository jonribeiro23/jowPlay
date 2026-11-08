"""FileSystemLibraryStorage em pastas temporárias.

A Lixeira é simulada, para não deixar arquivos de teste na Lixeira do usuário. O teste
com a Lixeira de verdade só roda com a variável de ambiente YTDOWN_TEST_RECYCLE_BIN=1.
"""

import os
import tempfile
import unittest
from pathlib import Path

from ytdown.domain.errors import LibraryError
from ytdown.domain.library_paths import library_path
from ytdown.infrastructure.library_storage import WINDOWS_MAX_PATH, FileSystemLibraryStorage
from ytdown.infrastructure.windows_shell import music_folder, send_to_recycle_bin


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / "Biblioteca"
        self.trashed = []
        self.storage = FileSystemLibraryStorage(self.root, trash_file=self.fake_trash)

    def fake_trash(self, path: Path):
        self.trashed.append(path)
        path.unlink()

    def new_file(self, name="novo.mp3", content=b"audio") -> Path:
        path = self.base / "temporaria" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def in_library(self, rel_path, content=b"audio") -> str:
        return self.storage.place(self.new_file(content=content), rel_path)


class PlaceTests(StorageTestCase):
    def test_creates_the_folders_and_moves_the_file(self):
        source = self.new_file()
        rel = self.storage.place(source, "Ana/Sol/01 - Manhã.mp3")
        self.assertEqual(rel, "Ana/Sol/01 - Manhã.mp3")
        self.assertEqual((self.root / "Ana" / "Sol" / "01 - Manhã.mp3").read_bytes(), b"audio")
        self.assertFalse(source.exists())
        self.assertTrue(self.storage.exists(rel))

    def test_never_overwrites_an_existing_file(self):
        self.in_library("Ana/Sol/x.mp3", b"primeiro")
        self.assertEqual(self.in_library("Ana/Sol/x.mp3", b"segundo"), "Ana/Sol/x (1).mp3")
        self.assertEqual(self.in_library("Ana/Sol/x.mp3", b"terceiro"), "Ana/Sol/x (2).mp3")
        self.assertEqual(self.storage.absolute("Ana/Sol/x.mp3").read_bytes(), b"primeiro")

    def test_paths_outside_the_library_are_refused(self):
        for rel in ("../fora.mp3", "Ana/../../fora.mp3", "C:/fora.mp3", "C:fora.mp3", "/fora.mp3",
                    "Ana\\..\\..\\fora.mp3", ""):
            with self.subTest(rel), self.assertRaises(LibraryError):
                self.storage.place(self.new_file(), rel)

    def test_missing_source_gives_a_readable_error(self):
        with self.assertRaises(LibraryError):
            self.storage.place(self.base / "nao-existe.mp3", "Ana/Sol/x.mp3")

    def test_paths_built_with_the_storage_limit_fit_windows(self):
        deep_root = self.base / ("pasta-com-nome-longo-" * 4) / "Biblioteca"
        storage = FileSystemLibraryStorage(deep_root)
        rel = library_path("A" * 80, "B" * 80, "C" * 300, 1, "flac", max_length=storage.max_relative_length())
        final = storage.place(self.new_file(), rel)
        self.assertLessEqual(len(str(storage.absolute(final))), WINDOWS_MAX_PATH)


class MoveTests(StorageTestCase):
    def test_moves_and_removes_folders_left_empty(self):
        rel = self.in_library("Ana/Sol/x.mp3")
        self.assertEqual(self.storage.move(rel, "Bia/Lua/x.mp3"), "Bia/Lua/x.mp3")
        self.assertTrue(self.storage.exists("Bia/Lua/x.mp3"))
        self.assertFalse((self.root / "Ana").exists())
        self.assertTrue(self.root.exists())

    def test_keeps_folders_that_still_have_files(self):
        rel = self.in_library("Ana/Sol/x.mp3")
        self.in_library("Ana/Sol/y.mp3")
        self.storage.move(rel, "Ana/Lua/x.mp3")
        self.assertTrue((self.root / "Ana" / "Sol" / "y.mp3").exists())

    def test_never_overwrites_on_move(self):
        rel = self.in_library("Ana/Sol/x.mp3", b"movido")
        self.in_library("Bia/Lua/x.mp3", b"existente")
        self.assertEqual(self.storage.move(rel, "Bia/Lua/x.mp3"), "Bia/Lua/x (1).mp3")
        self.assertEqual(self.storage.absolute("Bia/Lua/x.mp3").read_bytes(), b"existente")

    def test_renaming_only_the_letter_case_works(self):
        rel = self.in_library("Ana/Sol/manhã.mp3")
        self.assertEqual(self.storage.move(rel, "Ana/Sol/Manhã.mp3"), "Ana/Sol/Manhã.mp3")
        self.assertEqual([p.name for p in (self.root / "Ana" / "Sol").iterdir()], ["Manhã.mp3"])

    def test_same_path_is_a_no_op(self):
        rel = self.in_library("Ana/Sol/x.mp3")
        self.assertEqual(self.storage.move(rel, rel), rel)

    def test_missing_file_gives_a_readable_error(self):
        with self.assertRaises(LibraryError):
            self.storage.move("Ana/Sol/nao-existe.mp3", "Bia/x.mp3")


class TrashTests(StorageTestCase):
    def test_sends_to_the_trash_and_removes_empty_folders(self):
        rel = self.in_library("Ana/Sol/x.mp3")
        self.storage.trash(rel)
        self.assertEqual(self.trashed, [self.root / "Ana" / "Sol" / "x.mp3"])
        self.assertFalse((self.root / "Ana").exists())

    def test_failure_keeps_the_file(self):
        def broken_trash(path):
            raise OSError("Lixeira indisponível")

        storage = FileSystemLibraryStorage(self.root, trash_file=broken_trash)
        rel = self.in_library("Ana/Sol/x.mp3")
        with self.assertRaises(LibraryError):
            storage.trash(rel)
        self.assertTrue(storage.exists(rel))


class RelocateTests(StorageTestCase):
    def setUp(self):
        super().setUp()
        self.paths = [self.in_library(f"Artista {i}/Álbum/0{i} - Faixa.mp3", f"faixa {i}".encode()) for i in range(1, 4)]
        self.new_root = self.base / "Nova biblioteca"

    def test_moves_everything_with_progress(self):
        progress = []
        renamed = self.storage.relocate(self.new_root, lambda done, total: progress.append((done, total)))
        self.assertEqual(renamed, {})
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])
        self.assertEqual(self.storage.root, self.new_root)
        for i, rel in enumerate(self.paths, start=1):
            self.assertEqual(self.storage.absolute(rel).read_bytes(), f"faixa {i}".encode())
        self.assertEqual(list(self.root.iterdir()), [])  # Sobra só a pasta antiga, vazia.

    def test_existing_files_in_the_new_folder_are_never_overwritten(self):
        clash = self.new_root / "Artista 1" / "Álbum" / "01 - Faixa.mp3"
        clash.parent.mkdir(parents=True)
        clash.write_bytes(b"ja estava la")
        renamed = self.storage.relocate(self.new_root, lambda *_: None)
        self.assertEqual(renamed, {self.paths[0]: "Artista 1/Álbum/01 - Faixa (1).mp3"})
        self.assertEqual(clash.read_bytes(), b"ja estava la")

    def test_failure_puts_everything_back(self):
        locked = self.storage.absolute(self.paths[2])
        with open(locked, "rb"):  # No Windows, um arquivo aberto não pode ser movido.
            with self.assertRaises(LibraryError):
                self.storage.relocate(self.new_root, lambda *_: None)
        self.assertEqual(self.storage.root, self.root)
        for i, rel in enumerate(self.paths, start=1):
            self.assertEqual(self.storage.absolute(rel).read_bytes(), f"faixa {i}".encode())
        self.assertEqual([p for p in self.new_root.rglob("*") if p.is_file()], [])

    def test_new_folder_inside_the_current_one_is_refused(self):
        for target in (self.root / "Dentro", self.base):
            with self.subTest(target), self.assertRaises(LibraryError):
                self.storage.relocate(target, lambda *_: None)

    def test_same_folder_is_a_no_op(self):
        self.assertEqual(self.storage.relocate(self.root, lambda *_: None), {})
        self.assertTrue(self.storage.exists(self.paths[0]))


class WindowsShellTests(unittest.TestCase):
    def test_music_folder_exists(self):
        self.assertTrue(music_folder().is_dir())

    @unittest.skipUnless(os.environ.get("YTDOWN_TEST_RECYCLE_BIN") == "1", "deixa um arquivo na Lixeira real")
    def test_real_recycle_bin(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ytdown-teste-lixeira.txt"
            path.write_text("pode apagar", encoding="utf-8")
            send_to_recycle_bin(path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
