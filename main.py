"""Inicia o ytDown. Uso: python main.py (é também o ponto de entrada do PyInstaller)."""

import sys

from ytdown.bootstrap import run

if __name__ == "__main__":
    sys.exit(run())
