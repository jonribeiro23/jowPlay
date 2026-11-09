"""Caso de uso Playback: o único ponto que a interface usa para tocar música.

Une a fila (o que toca em seguida), o player (o som) e a biblioteca (onde está cada arquivo).
Toda a lógica roda sem som nos testes, com o FakeAudioPlayer.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from ytdown.application.ports import AudioPlayer, LibraryStorage, PlayerState
from ytdown.domain.errors import LibraryError
from ytdown.domain.library import Track
from ytdown.domain.play_queue import PlayQueue, RepeatMode


class PlaybackListener(Protocol):
    """Avisos para a interface (na thread da interface)."""

    def on_track_changed(self, track: Track | None) -> None:
        """A faixa atual mudou; None quando a fila acabou ou foi esvaziada."""

    def on_state_changed(self, state: PlayerState) -> None: ...

    def on_position_changed(self, position_ms: int, duration_ms: int) -> None: ...

    def on_queue_changed(self) -> None:
        """A fila mudou (itens, ordem, aleatório): a lista de reprodução precisa ser redesenhada."""

    def on_track_unavailable(self, track: Track, message: str) -> None:
        """A faixa não pôde ser tocada (ex.: o arquivo sumiu) e foi pulada."""


class Playback:
    def __init__(self, player: AudioPlayer, storage: LibraryStorage, rng: random.Random | None = None) -> None:
        self._player = player
        self._storage = storage
        self._queue: PlayQueue[Track] = PlayQueue(rng)
        self._listeners: list[PlaybackListener] = []
        self._loading = 0  # Muda a cada faixa carregada; avisos de faixas antigas são ignorados.
        self._failures = 0  # Faixas seguidas que não tocaram (para não girar para sempre).
        self._state = PlayerState.STOPPED
        player.set_listener(self)

    def add_listener(self, listener: PlaybackListener) -> None:
        self._listeners.append(listener)

    # --- consulta

    @property
    def current(self) -> Track | None:
        return self._queue.current

    @property
    def current_index(self) -> int | None:
        return self._queue.current_index

    @property
    def queue(self) -> list[Track]:
        return self._queue.items

    def upcoming(self) -> list[Track]:
        return self._queue.upcoming()

    @property
    def state(self) -> PlayerState:
        return self._state

    @property
    def position_ms(self) -> int:
        return self._player.position_ms

    @property
    def duration_ms(self) -> int:
        """A do player; enquanto ele carrega, a guardada na biblioteca."""
        current = self._queue.current
        return self._player.duration_ms or (current.duration_ms if current else 0)

    @property
    def volume(self) -> int:
        return self._player.volume

    @property
    def muted(self) -> bool:
        return self._player.muted

    @property
    def shuffle(self) -> bool:
        return self._queue.shuffle

    @property
    def repeat(self) -> RepeatMode:
        return self._queue.repeat

    # --- tocar

    def play_tracks(self, tracks: Iterable[Track], start: int = 0) -> None:
        """Troca a fila pelas faixas dadas (ex.: a lista de músicas) e toca a partir de `start`."""
        self._queue.replace(tracks, start)
        self._failures = 0
        self._notify_queue()
        self._start(self._queue.current)

    def play_pause(self) -> None:
        if self._state is PlayerState.PLAYING:
            self._player.pause()
        elif self._state is PlayerState.PAUSED:
            self._player.play()
        elif self._queue.current is not None:
            self._player.play()  # Parado (pelo botão Parar): toca a mesma faixa do começo.
        else:
            self._start(self._queue.next(manual=True))  # A fila tinha acabado: recomeça.

    def stop(self) -> None:
        self._player.stop()

    def next(self) -> None:
        self._failures = 0
        self._start(self._queue.next(manual=True))

    def previous(self) -> None:
        """Com mais de 3 s de faixa, recomeça a faixa; senão, volta para a anterior."""
        before = self._queue.current_index  # Posição, não faixa: a mesma faixa pode estar duas vezes.
        track = self._queue.previous(self._player.position_ms)
        if track is None:
            return
        if self._queue.current_index == before:  # Recomeça a mesma faixa, sem recarregar o arquivo.
            self._player.seek(0)
            if self._state is not PlayerState.PLAYING:
                self._player.play()
            return
        self._failures = 0
        self._start(track)

    def seek(self, position_ms: int) -> None:
        self._player.seek(position_ms)

    def set_volume(self, volume: int) -> None:
        self._player.set_volume(volume)

    def set_muted(self, muted: bool) -> None:
        self._player.set_muted(muted)

    def set_shuffle(self, on: bool) -> None:
        self._queue.shuffle = on
        self._notify_queue()

    def cycle_repeat(self) -> RepeatMode:
        return self._queue.cycle_repeat()

    # --- editar a fila

    def append(self, tracks: Iterable[Track]) -> None:
        self._queue.append(tracks)
        self._notify_queue()

    def play_next(self, tracks: Iterable[Track]) -> None:
        self._queue.play_next(tracks)
        self._notify_queue()

    def select(self, index: int) -> None:
        """Tocar uma faixa da lista de reprodução (ex.: duplo clique)."""
        self._failures = 0
        self._start(self._queue.select(index))

    def remove(self, index: int) -> None:
        """Tirar da fila. Se era a faixa atual, passa para a seguinte (tocando, se estava tocando)."""
        was_playing = self._state is PlayerState.PLAYING
        if self._queue.remove(index):
            if was_playing:
                self._start(self._queue.current)
            else:
                self._player.stop()
                self._load(self._queue.current)
        self._notify_queue()

    def move(self, from_index: int, to_index: int) -> None:
        self._queue.move(from_index, to_index)
        self._notify_queue()

    def clear(self) -> None:
        self._queue.clear()
        self._player.stop()
        self._loading += 1
        self._notify_queue()
        self._notify(lambda listener: listener.on_track_changed(None))

    # --- avisos do player (PlayerListener)

    def on_position(self, position_ms: int) -> None:
        if position_ms > 0:
            self._failures = 0  # Tocou de verdade.
        self._notify(lambda listener: listener.on_position_changed(position_ms, self.duration_ms))

    def on_duration(self, duration_ms: int) -> None:
        self._notify(lambda listener: listener.on_position_changed(self._player.position_ms, self.duration_ms))

    def on_state(self, state: PlayerState) -> None:
        self._state = state
        self._notify(lambda listener: listener.on_state_changed(state))

    def on_finished(self) -> None:
        """A faixa terminou sozinha: a fila decide o que vem (a mesma, com "repetir uma")."""
        self._start(self._queue.next(manual=False))

    def on_error(self, message: str) -> None:
        track = self._queue.current
        if track is None:
            return
        self._notify(lambda listener: listener.on_track_unavailable(track, message))
        self._failures += 1
        if self._failures >= len(self._queue):
            # Nenhuma faixa da fila toca: parar, em vez de girar para sempre.
            self._player.stop()
            return
        # Como "próxima" pedida pelo usuário: com "repetir uma", não insiste na mesma faixa.
        self._start(self._queue.next(manual=True))

    # --- detalhes

    def _start(self, track: Track | None) -> None:
        """Carrega e toca `track`; None significa fim da fila."""
        if self._load(track):
            self._player.play()

    def _load(self, track: Track | None) -> bool:
        """Carrega sem tocar. Devolve False se não há o que tocar ou se a faixa falhou ao carregar
        (nesse caso, o aviso de erro já tratou de pular para outra).
        """
        self._loading += 1
        loading = self._loading
        self._notify(lambda listener: listener.on_track_changed(track))
        if track is None:
            self._player.stop()
            return False
        try:
            path = self._storage.absolute(track.rel_path)
        except LibraryError:
            path = Path(track.rel_path)  # Caminho inválido: o player avisa que não encontrou.
        self._player.load(path)
        return loading == self._loading  # Um erro durante o load já carregou outra faixa.

    def _notify_queue(self) -> None:
        self._notify(lambda listener: listener.on_queue_changed())

    def _notify(self, call) -> None:
        for listener in list(self._listeners):
            call(listener)
