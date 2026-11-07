"""Janela "Enviar para o celular". O servidor funciona apenas enquanto ela está aberta."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

import share


class SendDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, on_closed) -> None:
        super().__init__(parent)
        self.on_closed = on_closed
        self.changed = threading.Event()
        self.server = share.ShareServer(on_change=self.changed.set)

        self.title("Enviar para o celular")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.code = tk.StringVar()
        self.address = tk.StringVar()
        self._build_layout()

        self.server.start()  # ShareError é tratado por quem abre a janela.
        self.address.set(
            "Se o celular não encontrar o PC, digite este endereço no app: "
            f"{share.local_address()}:{self.server.port}"
        )
        self.changed.set()
        self._refresh_loop()

    def _build_layout(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)

        steps = (
            "1. Conecte o celular ao Wi-Fi da mesma rede deste PC.\n"
            "2. Abra o app ytDown no celular e escolha este PC.\n"
            "3. Na primeira vez, digite o código abaixo no celular.\n"
            "4. Toque em Baixar no áudio que aparecer na lista."
        )
        ttk.Label(frame, text=steps, justify="left").grid(row=0, column=0, sticky="w")

        ttk.Label(frame, text="Código de pareamento").grid(row=1, column=0, sticky="w", pady=(12, 0))
        code_font = tkfont.nametofont("TkDefaultFont").copy()
        code_font.configure(size=22, weight="bold")
        ttk.Label(frame, textvariable=self.code, font=code_font).grid(row=2, column=0, sticky="w")

        address_label = ttk.Label(frame, textvariable=self.address)
        address_label.grid(row=3, column=0, sticky="ew", pady=(8, 12))
        address_label.bind("<Configure>", lambda event: address_label.configure(wraplength=event.width))

        ttk.Label(frame, text="Áudios disponíveis para o celular").grid(row=4, column=0, sticky="w")
        self.files = ttk.Treeview(frame, columns=("name", "status"), show="headings", height=5)
        self.files.heading("name", text="Arquivo", anchor="w")
        self.files.heading("status", text="Situação", anchor="w")
        self.files.column("name", width=320, stretch=True)
        self.files.column("status", width=220, stretch=False)
        self.files.grid(row=5, column=0, sticky="nsew", pady=(2, 12))

        ttk.Label(
            frame,
            text="Se o Windows perguntar, permita o acesso em redes privadas.",
        ).grid(row=6, column=0, sticky="w", pady=(0, 12))

        ttk.Button(frame, text="Parar de compartilhar", command=self.close).grid(row=7, column=0, sticky="e")

    def add(self, path: Path) -> None:
        self.server.share(path)
        self.deiconify()
        self.lift()

    def _refresh_loop(self) -> None:
        if self.changed.is_set():
            self.changed.clear()
            code = self.server.pairing_code
            self.code.set(f"{code[:3]} {code[3:]}")
            self.files.delete(*self.files.get_children())
            for name, status in self.server.statuses():
                self.files.insert("", "end", values=(name, status))
        self.after(200, self._refresh_loop)

    def close(self) -> None:
        self.server.stop()
        self.on_closed()
        self.destroy()
