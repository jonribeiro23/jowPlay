"""Inicia o ytDown. Uso: python main.py (é também o ponto de entrada do PyInstaller).

Enquanto a migração para Qt não termina, `python main.py --legacy` abre a interface
Tkinter da versão 1.x, que ainda tem a extração e o envio para o celular.
"""

import sys

from ytdown.bootstrap import run, run_legacy

if __name__ == "__main__":
    if "--legacy" in sys.argv[1:]:
        run_legacy()
    else:
        sys.exit(run())
