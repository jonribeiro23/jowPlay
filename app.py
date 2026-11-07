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
import share
from send_dialog import SendDialog

APP_TITLE = "ytDown - Extrator de Áudio"
COLOR_ERROR = "#b00020"
COLOR_SUCCESS = "#1b7f3b"
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
TITLE_LABEL_SINGLE = "Nome (vazio: título do vídeo)"
TITLE_LABEL_BATCH = "Nome (com vários vídeos, cada áudio usa o título do próprio vídeo)"
MAX_FAILURES_SHOWN = 3  # Acima disso, o resumo ficaria grande demais para a janela.


def _focus_next(event: tk.Event) -> str:
    event.widget.tk_focusNext().focus_set()
    return "break"  # Sem isto, Tab inseriria um caractere de tabulação na caixa de texto.


def _focus_previous(event: tk.Event) -> str:
    event.widget.tk_focusPrev().focus_set()
    return "break"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.working = False
        self.closing = False
        self.batch_size = 0
        self.saved_files: list[Path] = []
        self.send_dialog: SendDialog | None = None

        self.dest = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.format_label = tk.StringVar(value=core.AUDIO_FORMATS[0].label)
        self.title = tk.StringVar()
        self.author = tk.StringVar()
        self.cover = tk.StringVar()
        self.status = tk.StringVar(value="Cole a URL de um ou mais vídeos do YouTube, uma por linha, para começar.")

        root.title(APP_TITLE)
        root.iconbitmap(default=str(RESOURCES / "icon.ico"))  # Vale também para as outras janelas.
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_layout()
        root.after(100, self._poll_events)

    def _build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="URLs do YouTube (uma por linha)").grid(row=0, column=0, columnspan=2, sticky="w")
        urls = ttk.Frame(frame)
        urls.grid(row=1, column=0, sticky="nsew", pady=(2, 12))
        urls.columnconfigure(0, weight=1)
        self.url_text = tk.Text(
            urls, height=4, width=60, wrap="none", undo=True, font="TkDefaultFont", relief="solid", borderwidth=1
        )
        self.url_text.grid(row=0, column=0, sticky="nsew")
        url_scroll = ttk.Scrollbar(urls, orient="vertical", command=self.url_text.yview)
        url_scroll.grid(row=0, column=1, sticky="ns")
        self.url_text.configure(yscrollcommand=url_scroll.set)
        self.paste_button = ttk.Button(frame, text="Colar", command=self._paste_urls)
        self.paste_button.grid(row=1, column=1, padx=(8, 0), pady=(2, 12), sticky="n")

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

        self.title_label = ttk.Label(details, text=TITLE_LABEL_SINGLE)
        self.title_label.grid(row=0, column=0, columnspan=2, sticky="w")
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

        # Lista da fila: aparece apenas quando há mais de um vídeo.
        self.queue_frame = ttk.Frame(frame)
        self.queue_frame.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(0, 12))
        self.queue_frame.columnconfigure(0, weight=1)
        self.queue = ttk.Treeview(self.queue_frame, columns=("video", "status"), show="headings", height=5)
        self.queue.heading("video", text="Vídeo", anchor="w")
        self.queue.heading("status", text="Situação", anchor="w")
        self.queue.column("video", width=260, stretch=True)
        self.queue.column("status", width=200, stretch=True)
        self.queue.grid(row=0, column=0, sticky="nsew")
        queue_scroll = ttk.Scrollbar(self.queue_frame, orient="vertical", command=self.queue.yview)
        queue_scroll.grid(row=0, column=1, sticky="ns")
        self.queue.configure(yscrollcommand=queue_scroll.set)
        self.queue_frame.grid_remove()

        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.grid(row=8, column=0, columnspan=2, sticky="ew")
        self.status_label = ttk.Label(frame, textvariable=self.status)
        self.status_label.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(6, 12))
        self.status_label.bind(
            "<Configure>", lambda event: self.status_label.configure(wraplength=event.width)
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=10, column=0, columnspan=2, sticky="e")
        self.open_button = ttk.Button(
            buttons, text="Mostrar arquivo", command=self._show_file, state="disabled"
        )
        self.open_button.grid(row=0, column=0, padx=(0, 8))
        self.send_button = ttk.Button(
            buttons, text="Enviar para o celular", command=self._send_to_phone, state="disabled"
        )
        self.send_button.grid(row=0, column=1, padx=(0, 8))
        self.main_button = ttk.Button(buttons, text="Extrair áudio", command=self._on_main_button)
        self.main_button.grid(row=0, column=2)

        self.url_text.bind("<Tab>", _focus_next)
        self.url_text.bind("<Shift-Tab>", _focus_previous)
        self.url_text.bind("<Control-Return>", self._on_ctrl_enter)  # Enter sozinho pula linha.
        self.url_text.bind("<<Modified>>", self._on_urls_changed)
        for entry in (self.dest_entry, self.title_entry, self.author_entry, self.cover_entry):
            entry.bind("<Return>", self._on_enter)
        self.url_text.focus_set()

    def _url_text(self) -> str:
        return self.url_text.get("1.0", "end-1c")

    def _paste_urls(self) -> None:
        try:
            pasted = self.root.clipboard_get().strip()
        except tk.TclError:
            return  # Área de transferência vazia ou sem texto.
        current = self._url_text()
        if not current.strip():
            self.url_text.delete("1.0", "end")
        elif not current.endswith("\n"):
            pasted = "\n" + pasted
        self.url_text.insert("end", pasted)
        self.url_text.see("end")

    def _on_urls_changed(self, _event: tk.Event) -> None:
        self.url_text.edit_modified(False)  # Rearma o evento para a próxima alteração.
        self._refresh_title_field()

    def _refresh_title_field(self) -> None:
        """Com vários vídeos, um único nome para todos não faz sentido."""
        lines = [line for line in self._url_text().splitlines() if line.strip()]
        batch = len(lines) > 1
        self.title_label.configure(text=TITLE_LABEL_BATCH if batch else TITLE_LABEL_SINGLE)
        if not self.working:
            self.title_entry.configure(state="disabled" if batch else "normal")

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
        existing = [path for path in self.saved_files if path.exists()]
        if existing:
            subprocess.Popen(f'explorer /select,"{existing[-1]}"')

    def _send_to_phone(self) -> None:
        if not self.saved_files:
            return
        if self.send_dialog is None:
            try:
                self.send_dialog = SendDialog(self.root, on_closed=self._on_send_dialog_closed)
            except share.ShareError as exc:
                self._set_status(str(exc), COLOR_ERROR)
                return
        for path in self.saved_files:
            self.send_dialog.add(path)

    def _on_send_dialog_closed(self) -> None:
        self.send_dialog = None

    def _on_enter(self, _event: tk.Event) -> None:
        if not self.working:
            self._start()

    def _on_ctrl_enter(self, event: tk.Event) -> str:
        self._on_enter(event)
        return "break"

    def _on_main_button(self) -> None:
        if self.working:
            self.cancel.set()
            self.main_button.configure(state="disabled")
            self._set_status("Cancelando...")
        else:
            self._start()

    def _show_error(self, message: str) -> None:
        self._finish_progress(0)
        self._set_status(message, COLOR_ERROR)

    def _start(self) -> None:
        urls, invalid = core.parse_url_list(self._url_text())
        dest = Path(self.dest.get().strip())
        if len(invalid) == 1:
            self._show_error(f"A linha {invalid[0]} não parece ser uma URL do YouTube. Confira e tente de novo.")
            return
        if invalid:
            lines = ", ".join(str(number) for number in invalid)
            self._show_error(f"As linhas {lines} não parecem ser URLs do YouTube. Confira e tente de novo.")
            return
        if not urls:
            self._show_error("Cole a URL de pelo menos um vídeo do YouTube.")
            return
        if not dest.is_absolute():
            self._show_error("Escolha uma pasta válida para salvar o áudio.")
            return

        audio_format = next(f for f in core.AUDIO_FORMATS if f.label == self.format_label.get())
        cover = self.cover.get().strip().strip('"')  # "Copiar como caminho" inclui aspas.
        metadata = core.AudioMetadata(
            title=self.title.get().strip() if len(urls) == 1 else "",
            author=self.author.get().strip(),
            cover=Path(cover) if cover else None,
        )
        self.cancel.clear()
        self.saved_files = []
        self.batch_size = len(urls)
        self._fill_queue(urls)
        self._set_working(True)
        self._set_progress(core.Progress("Iniciando..."))
        threading.Thread(target=self._worker, args=(urls, dest, audio_format, metadata), daemon=True).start()

    def _fill_queue(self, urls: list[str]) -> None:
        self.queue.delete(*self.queue.get_children())
        if len(urls) == 1:
            self.queue_frame.grid_remove()
            return
        for index, url in enumerate(urls):
            self.queue.insert("", "end", iid=str(index), values=(url, "Na fila"))
        self.queue_frame.grid()

    def _worker(
        self, urls: list[str], dest: Path, audio_format: core.AudioFormat, metadata: core.AudioMetadata
    ) -> None:
        try:
            results = core.extract_batch(
                urls,
                dest,
                audio_format,
                metadata,
                on_progress=lambda index, progress: self.events.put(("progress", (index, progress))),
                on_result=lambda index, result: self.events.put(("item", (index, result))),
                cancel=self.cancel,
            )
            self.events.put(("finished", results))
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
            index, progress = value
            if not self.cancel.is_set():
                self._show_item_progress(index, progress)
        elif kind == "item":
            self._show_item_result(*value)
        elif kind == "finished":
            self._finish(value)
        else:
            self._set_working(False)
            self._show_error(f"Não foi possível extrair o áudio.\n{value}")

    def _show_item_progress(self, index: int, progress: core.Progress) -> None:
        if self.batch_size == 1:
            self._set_progress(progress)
            return
        # Na fila, a barra mostra o andamento total, não o do vídeo atual.
        done_fraction = (progress.percent or 0) / 100
        self._set_progress(
            core.Progress(
                f"Vídeo {index + 1} de {self.batch_size}: {progress.message}",
                (index + done_fraction) / self.batch_size * 100,
            )
        )
        self.queue.set(str(index), "status", progress.message)
        self.queue.see(str(index))

    def _show_item_result(self, index: int, result: core.BatchResult) -> None:
        if self.batch_size == 1:
            return
        if result.path:
            self.queue.item(str(index), values=(result.path.name, "Salvo"))
        elif result.cancelled:
            self.queue.set(str(index), "status", "Cancelado")
        else:
            self.queue.set(str(index), "status", f"Falhou: {result.error}")

    def _finish(self, results: list[core.BatchResult]) -> None:
        self._set_working(False)
        self.saved_files = [result.path for result in results if result.path]
        if self.saved_files:
            # Essas informações são destes vídeos; não podem ir para os próximos sem querer.
            for field in (self.title, self.author, self.cover):
                field.set("")
            self.open_button.configure(state="normal")
            self.send_button.configure(state="normal")

        if len(results) == 1:
            result = results[0]
            if result.path:
                self._finish_progress(100)
                self._set_status(f"Pronto! Áudio salvo em:\n{result.path}", COLOR_SUCCESS)
            elif result.cancelled:
                self._finish_progress(0)
                self._set_status("Extração cancelada.")
            else:
                self._show_error(f"Não foi possível extrair o áudio.\n{result.error}")
            return

        saved = len(self.saved_files)
        failed = sum(1 for result in results if result.error)
        cancelled = sum(1 for result in results if result.cancelled)
        lines = [f"{saved} de {len(results)} áudios salvos em:\n{self.dest.get().strip()}"]
        if failed:
            lines.append(f"{failed} {'vídeo falhou' if failed == 1 else 'vídeos falharam'}:")
            # A coluna da lista corta textos longos; aqui o motivo aparece inteiro.
            failures = [result for result in results if result.error]
            lines += [f"• {result.url}\n   {result.error}" for result in failures[:MAX_FAILURES_SHOWN]]
            if len(failures) > MAX_FAILURES_SHOWN:
                lines.append(f"• e mais {len(failures) - MAX_FAILURES_SHOWN} (veja a lista).")
        if cancelled:
            lines.append(f"Extração cancelada: {cancelled} {'vídeo não foi extraído' if cancelled == 1 else 'vídeos não foram extraídos'}.")
        if saved == len(results):
            lines[0] = "Pronto! " + lines[0]
        color = COLOR_SUCCESS if saved == len(results) else (COLOR_ERROR if failed else "")
        self._finish_progress((len(results) - cancelled) / len(results) * 100)
        self._set_status("\n".join(lines), color)

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
            self.url_text,
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
            self.send_button.configure(state="disabled")
        else:
            self._refresh_title_field()

    def _on_close(self) -> None:
        if self.send_dialog:
            self.send_dialog.close()
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
