"""Janela principal. A extração roda em outra thread para a janela não travar;
a thread conversa com a janela apenas pela fila `events`.
"""

from __future__ import annotations

import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from ytdown.application.extraction import ExtractBatch
from ytdown.domain.errors import ShareError
from ytdown.domain.models import AUDIO_FORMATS, AudioFormat, AudioMetadata, BatchResult, Progress, Stage
from ytdown.domain.urls import parse_url_list
from ytdown.presentation import texts
from ytdown.presentation.send_dialog import SendDialog, ShareServerFactory

APP_TITLE = "ytDown - Extrator de Áudio"
TONE_COLORS = {texts.Tone.NEUTRAL: "", texts.Tone.SUCCESS: "#1b7f3b", texts.Tone.ERROR: "#b00020"}
POLL_MS = 100
COVER_TYPES = [("Imagens", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"), ("Todos os arquivos", "*.*")]


def _focus_next(event: tk.Event) -> str:
    event.widget.tk_focusNext().focus_set()
    return "break"  # Sem isto, Tab inseriria um caractere de tabulação na caixa de texto.


def _focus_previous(event: tk.Event) -> str:
    event.widget.tk_focusPrev().focus_set()
    return "break"


class MainWindow:
    def __init__(self, root: tk.Tk, extract_batch: ExtractBatch, create_share_server: ShareServerFactory) -> None:
        self.root = root
        self._extract_batch = extract_batch
        self._create_share_server = create_share_server
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.working = False
        self.closing = False
        self.batch_size = 0
        self.running_format = AUDIO_FORMATS[0]
        self.saved_files: list[Path] = []
        self.send_dialog: SendDialog | None = None

        self.dest = tk.StringVar(value=texts.default_destination())
        self.format_label = tk.StringVar(value=AUDIO_FORMATS[0].label)
        self.title = tk.StringVar()
        self.author = tk.StringVar()
        self.cover = tk.StringVar()
        self.status = tk.StringVar(value=texts.WELCOME)

        root.title(APP_TITLE)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_layout()
        self._bind_keys()
        root.after(POLL_MS, self._poll_events)

    # --- montagem

    def _build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self._build_url_box(frame)
        self._build_format_and_destination(frame)
        self._build_details(frame)
        self._build_queue(frame)

        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.grid(row=8, column=0, columnspan=2, sticky="ew")
        self.status_label = ttk.Label(frame, textvariable=self.status)
        self.status_label.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(6, 12))
        self.status_label.bind("<Configure>", lambda event: self.status_label.configure(wraplength=event.width))

        self._build_buttons(frame)

    def _build_url_box(self, frame: ttk.Frame) -> None:
        ttk.Label(frame, text="URLs do YouTube (uma por linha)").grid(row=0, column=0, columnspan=2, sticky="w")
        box = ttk.Frame(frame)
        box.grid(row=1, column=0, sticky="nsew", pady=(2, 12))
        box.columnconfigure(0, weight=1)
        self.url_text = tk.Text(
            box, height=4, width=60, wrap="none", undo=True, font="TkDefaultFont", relief="solid", borderwidth=1
        )
        self.url_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.url_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.url_text.configure(yscrollcommand=scroll.set)
        self.paste_button = ttk.Button(frame, text="Colar", command=self._paste_urls)
        self.paste_button.grid(row=1, column=1, padx=(8, 0), pady=(2, 12), sticky="n")

    def _build_format_and_destination(self, frame: ttk.Frame) -> None:
        ttk.Label(frame, text="Formato").grid(row=2, column=0, columnspan=2, sticky="w")
        self.format_box = ttk.Combobox(
            frame, textvariable=self.format_label, values=[f.label for f in AUDIO_FORMATS], state="readonly"
        )
        self.format_box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 12))

        ttk.Label(frame, text="Salvar em").grid(row=4, column=0, columnspan=2, sticky="w")
        self.dest_entry = ttk.Entry(frame, textvariable=self.dest)
        self.dest_entry.grid(row=5, column=0, sticky="ew", pady=(2, 12))
        self.browse_button = ttk.Button(frame, text="Procurar...", command=self._choose_folder)
        self.browse_button.grid(row=5, column=1, padx=(8, 0), pady=(2, 12))

    def _build_details(self, frame: ttk.Frame) -> None:
        details = ttk.LabelFrame(frame, text="Informações do áudio (opcional)", padding=10)
        details.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        details.columnconfigure(0, weight=1)

        self.title_label = ttk.Label(details, text=texts.TITLE_LABEL_SINGLE)
        self.title_label.grid(row=0, column=0, columnspan=2, sticky="w")
        self.title_entry = ttk.Entry(details, textvariable=self.title)
        self.title_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        ttk.Label(details, text="Autor (vazio: sem autor)").grid(row=2, column=0, columnspan=2, sticky="w")
        self.author_entry = ttk.Entry(details, textvariable=self.author)
        self.author_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        ttk.Label(details, text="Imagem de capa (vazio: imagem padrão)").grid(
            row=4, column=0, columnspan=2, sticky="w"
        )
        self.cover_entry = ttk.Entry(details, textvariable=self.cover)
        self.cover_entry.grid(row=5, column=0, sticky="ew", pady=(2, 0))
        self.cover_button = ttk.Button(details, text="Procurar...", command=self._choose_cover)
        self.cover_button.grid(row=5, column=1, padx=(8, 0), pady=(2, 0))

    def _build_queue(self, frame: ttk.Frame) -> None:
        """Lista da fila: aparece apenas quando há mais de um vídeo."""
        self.queue_frame = ttk.Frame(frame)
        self.queue_frame.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(0, 12))
        self.queue_frame.columnconfigure(0, weight=1)
        self.queue = ttk.Treeview(self.queue_frame, columns=("video", "status"), show="headings", height=5)
        self.queue.heading("video", text="Vídeo", anchor="w")
        self.queue.heading("status", text="Situação", anchor="w")
        self.queue.column("video", width=260, stretch=True)
        self.queue.column("status", width=200, stretch=True)
        self.queue.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.queue_frame, orient="vertical", command=self.queue.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.queue.configure(yscrollcommand=scroll.set)
        self.queue_frame.grid_remove()

    def _build_buttons(self, frame: ttk.Frame) -> None:
        buttons = ttk.Frame(frame)
        buttons.grid(row=10, column=0, columnspan=2, sticky="e")
        self.open_button = ttk.Button(buttons, text="Mostrar arquivo", command=self._show_file, state="disabled")
        self.open_button.grid(row=0, column=0, padx=(0, 8))
        self.send_button = ttk.Button(
            buttons, text="Enviar para o celular", command=self._send_to_phone, state="disabled"
        )
        self.send_button.grid(row=0, column=1, padx=(0, 8))
        self.main_button = ttk.Button(buttons, text="Extrair áudio", command=self._on_main_button)
        self.main_button.grid(row=0, column=2)

    def _bind_keys(self) -> None:
        self.url_text.bind("<Tab>", _focus_next)
        self.url_text.bind("<Shift-Tab>", _focus_previous)
        self.url_text.bind("<Control-Return>", self._on_ctrl_enter)  # Enter sozinho pula linha.
        self.url_text.bind("<<Modified>>", self._on_urls_changed)
        for entry in (self.dest_entry, self.title_entry, self.author_entry, self.cover_entry):
            entry.bind("<Return>", self._on_enter)
        self.url_text.focus_set()

    # --- campos

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
        batch = sum(1 for line in self._url_text().splitlines() if line.strip()) > 1
        self.title_label.configure(text=texts.TITLE_LABEL_BATCH if batch else texts.TITLE_LABEL_SINGLE)
        if not self.working:
            self.title_entry.configure(state="disabled" if batch else "normal")

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.dest.get(), title="Salvar áudio em")
        if folder:
            self.dest.set(str(Path(folder)))

    def _choose_cover(self) -> None:
        image = filedialog.askopenfilename(title="Escolher imagem de capa", filetypes=COVER_TYPES)
        if image:
            self.cover.set(str(Path(image)))

    def _metadata(self) -> AudioMetadata:
        cover = self.cover.get().strip().strip('"')  # "Copiar como caminho" inclui aspas.
        return AudioMetadata(
            title=self.title.get().strip(),
            artist=self.author.get().strip(),
            cover=Path(cover) if cover else None,
        )

    def _selected_format(self) -> AudioFormat:
        return next(f for f in AUDIO_FORMATS if f.label == self.format_label.get())

    # --- ações

    def _show_file(self) -> None:
        existing = [path for path in self.saved_files if path.exists()]
        if existing:
            subprocess.Popen(f'explorer /select,"{existing[-1]}"')

    def _send_to_phone(self) -> None:
        if not self.saved_files:
            return
        if self.send_dialog is None:
            try:
                self.send_dialog = SendDialog(self.root, self._create_share_server, self._on_send_dialog_closed)
            except ShareError as exc:
                self._show(texts.Message(str(exc), texts.Tone.ERROR))
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
            self._show(texts.Message(texts.CANCELLING))
        else:
            self._start()

    def _start(self) -> None:
        urls, invalid_lines = parse_url_list(self._url_text())
        problem = texts.url_problem(urls, invalid_lines)
        dest = Path(self.dest.get().strip())
        if problem is None and not dest.is_absolute():
            problem = texts.INVALID_DESTINATION
        if problem:
            self._finish_progress(0)
            self._show(problem)
            return

        self.cancel.clear()
        self.saved_files = []
        self.batch_size = len(urls)
        self.running_format = self._selected_format()
        self._fill_queue(urls)
        self._set_working(True)
        starting = Progress(Stage.STARTING)
        self._set_progress(starting, texts.progress_text(starting, self.running_format))
        threading.Thread(
            target=self._worker, args=(urls, dest, self.running_format, self._metadata()), daemon=True
        ).start()

    def _worker(self, urls: list[str], dest: Path, audio_format: AudioFormat, metadata: AudioMetadata) -> None:
        try:
            results = self._extract_batch(
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

    # --- eventos da thread de extração

    def _poll_events(self) -> None:
        try:
            while True:
                self._handle_event(*self.events.get_nowait())
        except queue.Empty:
            pass
        if self.closing and not self.working:
            self.root.destroy()
            return
        self.root.after(POLL_MS, self._poll_events)

    def _handle_event(self, kind: str, value) -> None:
        if kind == "progress":
            if not self.cancel.is_set():
                self._show_item_progress(*value)
        elif kind == "item":
            self._show_item_result(*value)
        elif kind == "finished":
            self._finish(value)
        else:
            self._set_working(False)
            self._finish_progress(0)
            self._show(texts.extraction_failed(value))

    def _show_item_progress(self, index: int, progress: Progress) -> None:
        fmt = self.running_format
        if self.batch_size == 1:
            self._set_progress(progress, texts.progress_text(progress, fmt))
            return
        self._set_progress(
            texts.queue_progress(index, self.batch_size, progress),
            texts.queue_progress_text(index, self.batch_size, progress, fmt),
        )
        self.queue.set(str(index), "status", texts.progress_text(progress, fmt))
        self.queue.see(str(index))

    def _show_item_result(self, index: int, result: BatchResult) -> None:
        if self.batch_size == 1:
            return
        if result.path:
            self.queue.set(str(index), "video", result.path.name)
        self.queue.set(str(index), "status", texts.queue_status(result))

    def _finish(self, results: list[BatchResult]) -> None:
        self._set_working(False)
        self.saved_files = [result.path for result in results if result.path]
        if self.saved_files:
            # Essas informações são destes vídeos; não podem ir para os próximos sem querer.
            for field in (self.title, self.author, self.cover):
                field.set("")
            self.open_button.configure(state="normal")
            self.send_button.configure(state="normal")
        self._finish_progress(texts.processed_percent(results))
        self._show(texts.result_summary(results, self.dest.get().strip()))

    # --- estado da janela

    def _fill_queue(self, urls: list[str]) -> None:
        self.queue.delete(*self.queue.get_children())
        if len(urls) == 1:
            self.queue_frame.grid_remove()
            return
        for index, url in enumerate(urls):
            self.queue.insert("", "end", iid=str(index), values=(url, texts.QUEUED))
        self.queue_frame.grid()

    def _set_progress(self, progress: Progress, text: str) -> None:
        if progress.percent is None:
            if str(self.progress["mode"]) != "indeterminate":
                self.progress.configure(mode="indeterminate")
                self.progress.start(15)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=progress.percent)
        self._show(texts.Message(text))

    def _finish_progress(self, value: float) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=value)

    def _show(self, message: texts.Message) -> None:
        self.status.set(message.text)
        self.status_label.configure(foreground=TONE_COLORS[message.tone])

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
