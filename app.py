"""Janela do ytDown. O download roda em outra thread para a janela não travar."""

from __future__ import annotations

import ctypes
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import core

APP_TITLE = "ytDown - Extrator de Áudio"
COLOR_ERROR = "#b00020"
COLOR_SUCCESS = "#1b7f3b"
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.working = False
        self.closing = False
        self.saved_file: Path | None = None

        self.url = tk.StringVar()
        self.dest = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.format_label = tk.StringVar(value=core.AUDIO_FORMATS[0].label)
        self.title = tk.StringVar()
        self.author = tk.StringVar()
        self.cover = tk.StringVar()
        self.status =tk.StringVar(value="Cole a URL de um vídeo do YouTube para começar.")

        root.title(APP_TITLE)
        root.iconbitmap(RESOURCES / "icon.ico")
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_layout()
        root.after(100, self._poll_events)

    def _build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="URL do YouTube").grid(row=0, column=0, columnspan=2, sticky="w")
        self.url_entry = ttk.Entry(frame, textvariable=self.url, width=60)
        self.url_entry.grid(row=1, column=0, sticky="ew", pady=(2, 12))
        self.paste_button = ttk.Button(frame, text="Colar", command=self._paste_url)
        self.paste_button.grid(row=1, column=1, padx=(8, 0), pady=(2, 12))

        ttk.Label(frame, text="Formato").grid(row=2, column=0, columnspan=2, sticky="w")
        self.format_box = ttk.Combobox(
            frame,
            textvariable=self.format_label,
            values=[f.label for f in core.AUDIO_FORMATS],
            state="readonly",
        )
        self.format_box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 12))

        ttk.Label(frame, text="Salvar em").grid(row=4, column=0, columnspan=2, sticky="w")
        self.dest_entry = ttk.Entry(frame, textvariable=self.dest)
        self.dest_entry.grid(row=5, column=0, sticky="ew", pady=(2, 12))
        self.browse_button = ttk.Button(frame, text="Procurar...", command=self._choose_folder)
        self.browse_button.grid(row=5, column=1, padx=(8, 0), pady=(2, 12))

        details = ttk.LabelFrame(frame, text="Informações do áudio (opcional)", padding=10)
        details.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        details.columnconfigure(0, weight=1)

        ttk.Label(details, text="Nome (vazio: título do vídeo)").grid(row=0, column=0, columnspan=2, sticky="w")
        self.title_entry = ttk.Entry(details, textvariable=self.title)
        self.title_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        ttk.Label(details, text="Autor (vazio: sem autor)").grid(row=2, column=0, columnspan=2, sticky="w")
        self.author_entry = ttk.Entry(details, textvariable=self.author)
        self.author_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        ttk.Label(details, text="Imagem de capa (vazio: imagem padrão)").grid(row=4, column=0, columnspan=2, sticky="w")
        self.cover_entry = ttk.Entry(details, textvariable=self.cover)
        self.cover_entry.grid(row=5, column=0, sticky="ew", pady=(2, 0))
        self.cover_button = ttk.Button(details, text="Procurar...", command=self._choose_cover)
        self.cover_button.grid(row=5, column=1, padx=(8, 0), pady=(2, 0))

        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.grid(row=7, column=0, columnspan=2, sticky="ew")
        self.status_label = ttk.Label(frame, textvariable=self.status)
        self.status_label.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(6, 12))
        self.status_label.bind(
            "<Configure>", lambda event: self.status_label.configure(wraplength=event.width)
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=9, column=0, columnspan=2, sticky="e")
        self.open_button = ttk.Button(
            buttons, text="Mostrar arquivo", command=self._show_file, state="disabled"
        )
        self.open_button.grid(row=0, column=0, padx=(0, 8))
        self.main_button = ttk.Button(buttons, text="Extrair áudio", command=self._on_main_button)
        self.main_button.grid(row=0, column=1)

        self.url_entry.bind("<Return>", self._on_enter)
        for entry in (self.dest_entry, self.title_entry, self.author_entry, self.cover_entry):
            entry.bind("<Return>", self._on_enter)
        self.url_entry.focus_set()

    def _paste_url(self) -> None:
        try:
            self.url.set(self.root.clipboard_get().strip())
        except tk.TclError:
            pass  # Área de transferência vazia ou sem texto.

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.dest.get(), title="Salvar áudio em")
        if folder:
            self.dest.set(str(Path(folder)))

    def _choose_cover(self) -> None:
        image = filedialog.askopenfilename(
            title="Escolher imagem de capa",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"), ("Todos os arquivos", "*.*")],
        )
        if image:
            self.cover.set(str(Path(image)))

    def _show_file(self) -> None:
        if self.saved_file and self.saved_file.exists():
            subprocess.Popen(f'explorer /select,"{self.saved_file}"')

    def _on_enter(self, _event: tk.Event) -> None:
        if not self.working:
            self._start()

    def _on_main_button(self) -> None:
        if self.working:
            self.cancel.set()
            self.main_button.configure(state="disabled")
            self._set_status("Cancelando...")
        else:
            self._start()

    def _start(self) -> None:
        url = self.url.get().strip()
        dest = Path(self.dest.get().strip())
        if not core.is_youtube_url(url):
            self._finish_progress(0)
            self._set_status("Essa URL não parece ser do YouTube. Confira o link e tente de novo.", COLOR_ERROR)
            return
        if not dest.is_absolute():
            self._finish_progress(0)
            self._set_status("Escolha uma pasta válida para salvar o áudio.", COLOR_ERROR)
            return

        audio_format = next(f for f in core.AUDIO_FORMATS if f.label == self.format_label.get())
        cover = self.cover.get().strip().strip('"')  # "Copiar como caminho" inclui aspas.
        metadata = core.AudioMetadata(
            title=self.title.get().strip(),
            author=self.author.get().strip(),
            cover=Path(cover) if cover else None,
        )
        self.cancel.clear()
        self.saved_file = None
        self._set_working(True)
        self._set_progress(core.Progress("Iniciando..."))
        threading.Thread(target=self._worker, args=(url, dest, audio_format, metadata), daemon=True).start()

    def _worker(self, url: str, dest: Path, audio_format: core.AudioFormat, metadata: core.AudioMetadata) -> None:
        try:
            path = core.extract_audio(
                url, dest, audio_format, lambda p: self.events.put(("progress", p)), self.cancel, metadata
            )
            self.events.put(("done", path))
        except core.ExtractionCancelled:
            self.events.put(("cancelled", None))
        except Exception as exc:  # Sem console: todo erro precisa aparecer na janela.
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        try:
            while True:
                self._handle_event(*self.events.get_nowait())
        except queue.Empty:
            pass
        if self.closing and not self.working:
            self.root.destroy()
            return
        self.root.after(100, self._poll_events)

    def _handle_event(self, kind: str, value) -> None:
        if kind == "progress":
            if not self.cancel.is_set():
                self._set_progress(value)
            return

        self._set_working(False)
        if kind == "done":
            self.saved_file = value
            # Essas informações são de um vídeo só; não podem ir para o próximo sem querer.
            for field in (self.title, self.author, self.cover):
                field.set("")
            self.open_button.configure(state="normal")
            self._finish_progress(100)
            self._set_status(f"Pronto! Áudio salvo em:\n{value}", COLOR_SUCCESS)
        elif kind == "cancelled":
            self._finish_progress(0)
            self._set_status("Extração cancelada.")
        else:
            self._finish_progress(0)
            self._set_status(f"Não foi possível extrair o áudio.\n{value}", COLOR_ERROR)

    def _set_progress(self, progress: core.Progress) -> None:
        if progress.percent is None:
            if str(self.progress["mode"]) != "indeterminate":
                self.progress.configure(mode="indeterminate")
                self.progress.start(15)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=progress.percent)
        self._set_status(progress.message)

    def _finish_progress(self, value: float) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=value)

    def _set_status(self, message: str, color: str = "") -> None:
        self.status.set(message)
        self.status_label.configure(foreground=color)

    def _set_working(self, working: bool) -> None:
        self.working = working
        state = "disabled" if working else "normal"
        for widget in (
            self.url_entry,
            self.dest_entry,
            self.paste_button,
            self.browse_button,
            self.title_entry,
            self.author_entry,
            self.cover_entry,
            self.cover_button,
        ):
            widget.configure(state=state)
        self.format_box.configure(state="disabled" if working else "readonly")
        self.main_button.configure(text="Cancelar" if working else "Extrair áudio", state="normal")
        if working:
            self.open_button.configure(state="disabled")

    def _on_close(self) -> None:
        if not self.working:
            self.root.destroy()
            return
        # Espera a thread terminar para que ela apague seus arquivos temporários.
        self.closing = True
        self.cancel.set()
        self.root.withdraw()


def main() -> None:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Evita texto borrado em telas com escala.
    root = tk.Tk()
    App(root)
    root.update_idletasks()
    root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
    root.mainloop()


if __name__ == "__main__":
    main()
