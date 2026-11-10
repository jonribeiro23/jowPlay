"""Interfaces que os casos de uso esperam; a camada infrastructure as implementa."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Protocol, ContextManager

from ytdown.domain.library import AlbumSummary, ArtistSummary, GenreSummary, Track, TrackQuery
from ytdown.domain.models import AudioFileInfo, AudioFormat, AudioTags, Progress
from ytdown.domain.sharing import TransferStatus
from ytdown.domain.playlist import Playlist

ProgressCallback = Callable[[Progress], None]


@dataclass(frozen=True)
class DownloadedAudio:
    path: Path
    title: str | None  # Título do vídeo, se a fonte informar.
    source_url: str | None  # Endereço canônico do vídeo (o mesmo para youtu.be/X e watch?v=X).


class AudioDownloader(Protocol):
    def download(
        self,
        url: str,
        work_dir: Path,
        audio_format: AudioFormat,
        on_progress: ProgressCallback,
        cancel: threading.Event,
    ) -> DownloadedAudio:
        """Baixa e converte o áudio dentro de `work_dir`.

        Falha com ExtractionError ou ExtractionCancelled.
        """


class CoverLoader(Protocol):
    def load(self, path: Path | None) -> bytes:
        """Devolve a capa pronta para gravar; sem `path`, a capa padrão. Falha com InvalidCover."""


class TagWriter(Protocol):
    def write(self, path: Path, tags: AudioTags) -> None:
        """Grava as etiquetas no arquivo; campos vazios removem as existentes. Falha com ExtractionError."""


class MetadataReader(Protocol):
    def read(self, path: Path) -> AudioFileInfo:
        """Lê as etiquetas e a duração. Arquivo sem etiquetas devolve só a duração.

        Falha com UnreadableAudio se o formato não tiver suporte ou o arquivo estiver corrompido.
        """

    def read_cover(self, path: Path) -> bytes | None:
        """Bytes da capa embutida (de preferência a da frente), ou None se não houver.

        Falha com UnreadableAudio, como `read`.
        """


class ThumbnailCache(Protocol):
    """Miniaturas derivadas: agendamento n?o bloqueia a interface."""

    def request(self, audio: Path) -> None:
        """Agenda gera??o ap?s registrar ou alterar a capa de um ?udio."""

    def get_or_create(self, audio: Path) -> Path | None:
        """Obt?m ou gera a miniatura; chamar fora da thread da interface."""

    def cleanup(self, audios: Iterable[Path]) -> int:
        """Remove ?rf?s ap?s examinar todos os ?udios; executar em segundo plano."""


class LibraryStorage(Protocol):
    """Os arquivos da pasta da biblioteca. Caminhos relativos usam "/" como separador.

    Nenhuma operação sobrescreve um arquivo existente: em caso de colisão, o nome
    ganha " (1)", " (2)"... e o caminho realmente usado é devolvido.
    """

    @property
    def root(self) -> Path: ...

    def is_available(self) -> bool:
        """Se a raiz gerenciada pode ser examinada agora."""

    def absolute(self, rel_path: str) -> Path: ...

    def exists(self, rel_path: str) -> bool: ...

    def max_relative_length(self) -> int:
        """Quantos caracteres um caminho relativo pode ter para o caminho completo caber no Windows."""

    def place(self, source: Path, rel_path: str) -> str:
        """Move um arquivo novo para a biblioteca. Falha com LibraryError."""

    def move(self, rel_path: str, new_rel_path: str) -> str:
        """Move um arquivo da biblioteca e apaga as pastas que ficarem vazias. Falha com LibraryError."""

    def trash(self, rel_path: str) -> None:
        """Envia o arquivo para a Lixeira e apaga as pastas que ficarem vazias. Falha com LibraryError."""

    def discard(self, rel_path: str) -> None:
        """Apaga de vez um arquivo que o app acabou de colocar (para desfazer um `place`) e as
        pastas que ficarem vazias. Não faz nada se ele não existir. Falha com LibraryError."""

    def relocate(self, new_root: Path, on_progress: Callable[[int, int], None]) -> dict[str, str]:
        """Move a biblioteca inteira para `new_root`, informando (movidos, total).

        Devolve {caminho antigo: caminho novo} dos arquivos que precisaram de outro nome.
        Se algo falhar, desfaz o que já foi movido e falha com LibraryError.
        """


class PlayerState(Enum):
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()


class PlayerListener(Protocol):
    """Avisos do player. Chegam na thread da interface, a mesma que chama o player."""

    def on_position(self, position_ms: int) -> None: ...

    def on_duration(self, duration_ms: int) -> None: ...

    def on_state(self, state: PlayerState) -> None: ...

    def on_finished(self) -> None:
        """A faixa chegou ao fim sozinha (não é chamado por `stop` nem ao trocar de faixa)."""

    def on_error(self, message: str) -> None:
        """A faixa não pode ser tocada (arquivo ausente, corrompido...). O player fica parado e
        continua utilizável: basta carregar outra faixa. `message` já é o texto para o usuário.
        """


class AudioPlayer(Protocol):
    """Toca um arquivo de áudio por vez. Carregar outro arquivo substitui o atual (nunca há
    dois tocando ao mesmo tempo). Nada aqui lança exceção: problemas viram `on_error`.
    """

    def set_listener(self, listener: PlayerListener) -> None: ...

    def load(self, path: Path) -> None:
        """Prepara o arquivo para tocar do começo, parando o anterior. Não começa a tocar."""

    def play(self) -> None: ...

    def pause(self) -> None: ...

    def stop(self) -> None:
        """Para e volta ao começo da faixa."""

    def seek(self, position_ms: int) -> None: ...

    @property
    def state(self) -> PlayerState: ...

    @property
    def position_ms(self) -> int: ...

    @property
    def duration_ms(self) -> int:
        """0 enquanto o arquivo não terminou de carregar."""

    @property
    def volume(self) -> int:
        """De 0 a 100, na escala que o ouvido percebe (o meio do controle soa como metade)."""

    def set_volume(self, volume: int) -> None: ...

    @property
    def muted(self) -> bool: ...

    def set_muted(self, muted: bool) -> None: ...


class Settings(Protocol):
    """Preferências do app, guardadas entre sessões. Valores precisam caber em JSON."""

    def get(self, key: str, default=None): ...

    def set(self, key: str, value) -> None: ...


class TrackRepository(Protocol):
    """Índice persistente da biblioteca.

    Os resultados de `list_tracks`, `artists`, `albums` e `genres` devem ser iguais aos das
    funções de referência em `ytdown.domain.library` (query_tracks, summarize_*). O teste
    de contrato em `tests/contracts/track_repository.py` verifica isso em cada implementação.
    """

    def add(self, track: Track) -> Track:
        """Salva uma faixa nova e a devolve com o `id` preenchido.

        Falha com ValueError se já existir uma faixa com o mesmo `rel_path`.
        """

    def update(self, track: Track) -> None:
        """Substitui todos os dados da faixa com o mesmo `id`. Falha com KeyError se ela não existir."""

    def record_play(self, track_id: int, played_at) -> Track | None:
        """Incrementa apenas as estatísticas atomicamente; devolve None se a faixa foi removida."""

    def remove(self, track_id: int) -> None:
        """Remove a faixa; não faz nada se ela não existir."""

    def get(self, track_id: int) -> Track | None: ...

    def find_by_source_url(self, url: str) -> Track | None: ...

    def find_by_path(self, rel_path: str) -> Track | None: ...

    def list_tracks(self, query: TrackQuery = TrackQuery()) -> list[Track]: ...

    def artists(self) -> list[ArtistSummary]: ...

    def albums(self, artist: str | None = None) -> list[AlbumSummary]:
        """Todos os álbuns ou, com `artist` (nome de exibição), só os desse artista."""

    def genres(self) -> list[GenreSummary]: ...


class PlaylistRepository(Protocol):
    def create(self, name: str, track_ids: Iterable[int] = ()) -> Playlist: ...
    def get(self, playlist_id: int) -> Playlist | None: ...
    def list_playlists(self) -> list[Playlist]: ...
    def rename(self, playlist_id: int, name: str) -> Playlist: ...
    def delete(self, playlist_id: int) -> None: ...
    def add_tracks(self, playlist_id: int, track_ids: Iterable[int]) -> Playlist: ...
    def remove_track(self, playlist_id: int, index: int) -> Playlist: ...
    def move_track(self, playlist_id: int, source: int, destination: int) -> Playlist: ...


class DeviceRegistry(Protocol):
    """Identidade deste PC e celulares pareados, guardados entre execuções do app."""

    @property
    def server_id(self) -> str: ...

    def add_device(self, name: str) -> str:
        """Registra um celular e devolve o token que ele usará daqui em diante."""

    def knows(self, token: str) -> bool: ...


class ShareServer(Protocol):
    """O que a interface precisa do servidor que entrega os áudios ao celular."""

    @property
    def port(self) -> int: ...

    @property
    def pairing_code(self) -> str: ...

    def start(self) -> None:
        """Falha com ShareError."""

    def stop(self) -> None: ...

    def address(self) -> str: ...

    def share(self, path: Path) -> None: ...

    def statuses(self) -> list[tuple[str, TransferStatus]]: ...


class ImportFiles(Protocol):
    """I/O cancelável da importação. tick informa atividade, inclusive por bloco."""

    def scan(self, folders: Iterable[Path], excluded: Path, cancel: threading.Event,
             tick: Callable[[], None]) -> tuple[list[Path], list[str]]: ...

    def fingerprint(self, path: Path, cancel: threading.Event, tick: Callable[[], None]) -> str: ...

    def staged(self, source: Path, root: Path, cancel: threading.Event, tick: Callable[[], None]) -> ContextManager[Path]:
        """Context manager: cópia completa temporária; sempre limpa ao sair."""
