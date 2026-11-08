"""Todos os textos que o usuário vê, montados a partir dos dados do domínio."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from ytdown.domain.library import Track
from ytdown.domain.models import AudioFormat, BatchResult, Progress, Stage
from ytdown.domain.sharing import TransferStatus

WELCOME = "Cole a URL de um ou mais vídeos do YouTube, uma por linha, para começar."
CANCELLING = "Cancelando..."
TITLE_LABEL_SINGLE = "Nome (vazio: título do vídeo)"
TITLE_LABEL_BATCH = "Nome (com vários vídeos, cada áudio usa o título do próprio vídeo)"
QUEUED = "Na fila"
MAX_FAILURES_SHOWN = 3  # Acima disso, o resumo ficaria grande demais para a janela.

TRANSFER_STATUS = {
    TransferStatus.WAITING: "Aguardando o celular",
    TransferStatus.SENDING: "Enviando...",
    TransferStatus.SENT: "Enviado",
    TransferStatus.FAILED: "Falhou; o celular pode tentar de novo",
}


class Tone(Enum):
    NEUTRAL = auto()
    SUCCESS = auto()
    ERROR = auto()


@dataclass(frozen=True)
class Message:
    text: str
    tone: Tone = Tone.NEUTRAL


def progress_text(progress: Progress, audio_format: AudioFormat) -> str:
    match progress.stage:
        case Stage.STARTING:
            return "Iniciando..."
        case Stage.FETCHING_INFO:
            return "Obtendo informações do vídeo..."
        case Stage.DOWNLOADING if progress.percent is not None:
            return f"Baixando... {progress.percent:.0f}%"
        case Stage.DOWNLOADING:
            return "Baixando..."
        case Stage.CONVERTING:
            return f"Convertendo para {audio_format.extension.upper()}..."
        case Stage.TAGGING:
            return "Gravando nome, autor e capa..."
        case Stage.SAVING:
            return "Salvando..."


def queue_progress(index: int, total: int, progress: Progress) -> Progress:
    """Na fila, a barra mostra o andamento total, não o do vídeo atual."""
    done_fraction = (progress.percent or 0) / 100
    return Progress(progress.stage, (index + done_fraction) / total * 100)


def queue_progress_text(index: int, total: int, progress: Progress, audio_format: AudioFormat) -> str:
    return f"Vídeo {index + 1} de {total}: {progress_text(progress, audio_format)}"


def queue_status(result: BatchResult) -> str:
    if result.path:
        return "Salvo"
    if result.cancelled:
        return "Cancelado"
    return f"Falhou: {result.error}"


def url_problem(urls: list[str], invalid_lines: list[int]) -> Message | None:
    """Mensagem de erro para a lista digitada, ou None se ela estiver boa."""
    if len(invalid_lines) == 1:
        return Message(
            f"A linha {invalid_lines[0]} não parece ser uma URL do YouTube. Confira e tente de novo.", Tone.ERROR
        )
    if invalid_lines:
        lines = ", ".join(str(number) for number in invalid_lines)
        return Message(f"As linhas {lines} não parecem ser URLs do YouTube. Confira e tente de novo.", Tone.ERROR)
    if not urls:
        return Message("Cole a URL de pelo menos um vídeo do YouTube.", Tone.ERROR)
    return None


INVALID_DESTINATION = Message("Escolha uma pasta válida para salvar o áudio.", Tone.ERROR)


def extraction_failed(reason: str) -> Message:
    return Message(f"Não foi possível extrair o áudio.\n{reason}", Tone.ERROR)


def result_summary(results: list[BatchResult], dest_dir: str) -> Message:
    if len(results) == 1:
        return _single_result(results[0])

    saved = sum(1 for result in results if result.path)
    failures = [result for result in results if result.error]
    cancelled = sum(1 for result in results if result.cancelled)

    lines = [f"{saved} de {len(results)} áudios salvos em:\n{dest_dir}"]
    if saved == len(results):
        lines[0] = "Pronto! " + lines[0]
    if failures:
        lines.append(f"{len(failures)} {'vídeo falhou' if len(failures) == 1 else 'vídeos falharam'}:")
        # A coluna da lista corta textos longos; aqui o motivo aparece inteiro.
        lines += [f"• {result.url}\n   {result.error}" for result in failures[:MAX_FAILURES_SHOWN]]
        if len(failures) > MAX_FAILURES_SHOWN:
            lines.append(f"• e mais {len(failures) - MAX_FAILURES_SHOWN} (veja a lista).")
    if cancelled:
        lines.append(
            f"Extração cancelada: {cancelled} "
            f"{'vídeo não foi extraído' if cancelled == 1 else 'vídeos não foram extraídos'}."
        )

    if saved == len(results):
        tone = Tone.SUCCESS
    elif failures:
        tone = Tone.ERROR
    else:
        tone = Tone.NEUTRAL
    return Message("\n".join(lines), tone)


def _single_result(result: BatchResult) -> Message:
    if result.path:
        return Message(f"Pronto! Áudio salvo em:\n{result.path}", Tone.SUCCESS)
    if result.cancelled:
        return Message("Extração cancelada.")
    return extraction_failed(result.error)


def processed_percent(results: list[BatchResult]) -> float:
    """Quanto da fila foi processado (salvo ou com falha) ao terminar."""
    if len(results) == 1:
        return 100 if results[0].path else 0
    return sum(1 for result in results if not result.cancelled) / len(results) * 100


def share_address(address: str) -> str:
    return f"Se o celular não encontrar o PC, digite este endereço no app: {address}"


def pairing_code(code: str) -> str:
    return f"{code[:3]} {code[3:]}"


def default_destination() -> str:
    return str(Path.home() / "Downloads")


# --- biblioteca

DUPLICATE_TITLE = "Já está na biblioteca"
REPLACE_LABEL = "Substituir"
KEEP_BOTH_LABEL = "Manter os dois"
CANCEL_LABEL = "Cancelar"
NOTHING_EXTRACTED = Message("Nada foi extraído.")
MAX_DUPLICATES_SHOWN = 5


def library_destination(folder: str) -> str:
    return (f"Os áudios vão para a biblioteca, organizados em Artista\\Álbum, na pasta:\n{folder}\n"
            "Para mudar a pasta, use Opções.")


def duplicate_question(duplicates: list[tuple[str, Track]]) -> str:
    """Pergunta única para os vídeos da fila que já estão na biblioteca."""
    names = [f"• {track.title} ({track.display_artist})" for _, track in duplicates[:MAX_DUPLICATES_SHOWN]]
    if len(duplicates) > MAX_DUPLICATES_SHOWN:
        names.append(f"• e mais {len(duplicates) - MAX_DUPLICATES_SHOWN}.")
    intro = ("Este vídeo já está na biblioteca:" if len(duplicates) == 1
             else f"{len(duplicates)} vídeos já estão na biblioteca:")
    return (f"{intro}\n" + "\n".join(names) + "\n\n"
            f"{REPLACE_LABEL}: o áudio novo fica no lugar do antigo (que vai para a Lixeira).\n"
            f"{KEEP_BOTH_LABEL}: o áudio novo entra na biblioteca ao lado do antigo.\n"
            f"{CANCEL_LABEL}: nada é extraído.")


OPTIONS_TITLE = "Opções"
LIBRARY_FOLDER_LABEL = "Pasta da biblioteca"
LIBRARY_FOLDER_HINT = ("Todo áudio extraído é guardado aqui, em Artista\\Álbum. "
                       "Ao mudar a pasta, os áudios que já estão na biblioteca vão junto.")
WAIT_FOR_EXTRACTION = Message("Espere a extração terminar para mudar a pasta da biblioteca.", Tone.ERROR)


def moving_library(done: int, total: int) -> str:
    return f"Movendo a biblioteca... {done} de {total} arquivos"


LIBRARY_MOVED = Message("Pronto! A biblioteca foi movida para a pasta acima.", Tone.SUCCESS)


def library_move_failed(reason: str) -> Message:
    return Message(f"A biblioteca não foi movida; nada mudou.\n{reason}", Tone.ERROR)
