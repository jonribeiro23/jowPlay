"""Garante a regra das camadas: cada uma só pode importar as que estão mais para dentro."""

import ast
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "ytdown"

# O que cada camada NÃO pode importar.
FORBIDDEN = {
    "domain": ("ytdown.application", "ytdown.infrastructure", "ytdown.presentation", "ytdown.bootstrap"),
    "application": ("ytdown.infrastructure", "ytdown.presentation", "ytdown.bootstrap"),
    "infrastructure": ("ytdown.presentation", "ytdown.bootstrap"),
    "presentation": ("ytdown.infrastructure", "ytdown.bootstrap"),
}
# As camadas de dentro também não dependem de bibliotecas de terceiros, de interface ou de rede.
OUTSIDE_LIBRARIES = ("yt_dlp", "mutagen", "PIL", "tkinter", "PySide6", "http", "socket", "socketserver", "sqlite3")


def imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def violations(layer: str, forbidden: tuple[str, ...]) -> list[str]:
    found = []
    for path in sorted((PACKAGE / layer).rglob("*.py")):
        for module in imported_modules(path):
            if any(module == name or module.startswith(name + ".") for name in forbidden):
                found.append(f"{path.relative_to(PACKAGE)} importa {module}")
    return found


PROJECT = PACKAGE.parent


class LayerTests(unittest.TestCase):
    def test_tkinter_is_gone(self):
        # A interface é só Qt desde a JOW-21; o Tkinter nem vai mais no pacote.
        sources = [PROJECT / "main.py", *PACKAGE.rglob("*.py"), *(PROJECT / "tests").rglob("*.py")]
        found = [str(path.relative_to(PROJECT)) for path in sources
                 if any(module.split(".")[0] in ("tkinter", "_tkinter") for module in imported_modules(path))]
        self.assertEqual(found, [])

    def test_layers_only_depend_inward(self):
        for layer, forbidden in FORBIDDEN.items():
            with self.subTest(layer):
                self.assertEqual(violations(layer, forbidden), [])

    def test_domain_and_application_do_not_use_outside_libraries(self):
        for layer in ("domain", "application"):
            with self.subTest(layer):
                self.assertEqual(violations(layer, OUTSIDE_LIBRARIES), [])


if __name__ == "__main__":
    unittest.main()
