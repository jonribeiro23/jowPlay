"""A fila de reprodução: o que toca agora e o que toca em seguida.

Regras puras, sem áudio nem interface. Quem toca de verdade (Playback, JOW-24) pergunta à
fila qual é o próximo item e manda o player tocá-lo do começo.

Há duas ordens:
- a da lista, que o usuário vê e reorganiza (`items`);
- a de reprodução, igual à da lista ou embaralhada quando o aleatório está ligado.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from enum import Enum, auto
from typing import Generic, TypeVar

T = TypeVar("T")

# "Anterior" com a faixa tocando há mais tempo que isso recomeça a faixa, como nos players comuns.
RESTART_THRESHOLD_MS = 3000


class RepeatMode(Enum):
    OFF = auto()  # No fim da fila, para.
    ALL = auto()  # No fim da fila, recomeça (reembaralhada, se o aleatório estiver ligado).
    ONE = auto()  # A faixa que termina toca de novo.


_NEXT_REPEAT = {RepeatMode.OFF: RepeatMode.ALL, RepeatMode.ALL: RepeatMode.ONE, RepeatMode.ONE: RepeatMode.OFF}


class _Entry(Generic[T]):
    """Um lugar na fila. A mesma faixa pode entrar duas vezes; cada entrada é distinta."""

    __slots__ = ("item",)

    def __init__(self, item: T) -> None:
        self.item = item


class PlayQueue(Generic[T]):
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._entries: list[_Entry[T]] = []  # Ordem da lista.
        self._order: list[_Entry[T]] = []  # Ordem de reprodução.
        self._current: _Entry[T] | None = None
        self._shuffle = False
        self.repeat = RepeatMode.OFF

    # --- consulta

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def items(self) -> list[T]:
        """Na ordem da lista."""
        return [entry.item for entry in self._entries]

    @property
    def current(self) -> T | None:
        """O item que está tocando (ou pausado); None se nada foi escolhido ou a fila acabou."""
        return self._current.item if self._current else None

    @property
    def current_index(self) -> int | None:
        """Posição do item atual na lista."""
        return self._entries.index(self._current) if self._current else None

    def upcoming(self) -> list[T]:
        """O que ainda vai tocar, na ordem de reprodução (sem contar a volta do "repetir todas")."""
        start = self._order.index(self._current) + 1 if self._current else 0
        return [entry.item for entry in self._order[start:]]

    # --- montagem da fila

    def replace(self, items: Iterable[T], start: int = 0) -> T | None:
        """Troca a fila inteira (ex.: tocar a seleção) e escolhe `start` como atual."""
        self._entries = [_Entry(item) for item in items]
        self._current = None
        if not self._entries:
            self._order = []
            return None
        if not 0 <= start < len(self._entries):
            raise IndexError(start)
        self._current = self._entries[start]
        self._rebuild_order()
        return self._current.item

    def append(self, items: Iterable[T]) -> None:
        """Acrescenta ao fim da lista. Com o aleatório, cada item entra num ponto sorteado do
        que ainda vai tocar, para não ficarem todos no fim.
        """
        new = [_Entry(item) for item in items]
        self._entries.extend(new)
        if not self._shuffle:
            self._order = list(self._entries)
            return
        first_free = self._order.index(self._current) + 1 if self._current else 0
        for entry in new:
            self._order.insert(self._rng.randint(first_free, len(self._order)), entry)

    def play_next(self, items: Iterable[T]) -> None:
        """"Tocar em seguida": os itens entram logo depois do atual, na ordem dada."""
        new = [_Entry(item) for item in items]
        at = self._entries.index(self._current) + 1 if self._current else 0
        self._entries[at:at] = new
        if not self._shuffle:
            self._order = list(self._entries)
            return
        at = self._order.index(self._current) + 1 if self._current else 0
        self._order[at:at] = new

    def remove(self, index: int) -> bool:
        """Tira o item da posição `index` da lista. Devolve True se era o atual: nesse caso,
        o atual passa a ser o que tocaria em seguida (ou nenhum, se a fila acabou).
        """
        entry = self._entries.pop(index)
        was_current = entry is self._current
        if was_current:
            position = self._order.index(entry)
            following = self._order[position + 1:] or (self._order[:position] if self.repeat is not RepeatMode.OFF
                                                        else [])
            self._current = following[0] if following else None
        self._order.remove(entry)
        return was_current

    def move(self, from_index: int, to_index: int) -> None:
        """Muda um item de lugar na lista. Sem o aleatório, muda também a ordem de reprodução."""
        entry = self._entries.pop(from_index)
        self._entries.insert(to_index, entry)
        if not self._shuffle:
            self._order = list(self._entries)

    def clear(self) -> None:
        self._entries, self._order, self._current = [], [], None

    # --- navegação

    def select(self, index: int) -> T:
        """O usuário escolheu um item da lista (ex.: duplo clique): ele passa a ser o atual.
        Com o aleatório, os que ainda não tocaram continuam na vez deles.
        """
        entry = self._entries[index]
        if self._shuffle and entry is not self._current:
            self._order.remove(entry)
            at = self._order.index(self._current) + 1 if self._current else 0
            self._order.insert(at, entry)
        self._current = entry
        return entry.item

    def next(self, manual: bool = False) -> T | None:
        """O item que toca agora: quando a faixa termina sozinha (`manual=False`) ou quando o
        usuário pede a próxima (`manual=True`). None quando a fila acaba (o player para).

        "Repetir uma" só vale quando a faixa termina sozinha; pedindo a próxima, o usuário quer
        mudar de faixa, e a fila dá a volta como em "repetir todas".
        """
        if not self._order:
            return None
        if self._current is None:  # Parada no fim (ou nunca começou): recomeça a fila.
            if self._shuffle:
                self._reshuffle()
            self._current = self._order[0]
            return self._current.item
        if self.repeat is RepeatMode.ONE and not manual:
            return self._current.item

        position = self._order.index(self._current)
        if position + 1 < len(self._order):
            self._current = self._order[position + 1]
        elif self.repeat is RepeatMode.ALL or (self.repeat is RepeatMode.ONE and manual):
            if self._shuffle:
                self._reshuffle(avoid_first=self._current)
            self._current = self._order[0]
        else:
            self._current = None  # Fim da fila.
            return None
        return self._current.item

    def previous(self, position_ms: int) -> T | None:
        """O item a tocar do começo quando o usuário pede a anterior.

        Se a faixa atual já tocou mais de 3 segundos, ela mesma recomeça. Senão, volta para a
        anterior; na primeira da fila, recomeça a atual (ou vai para a última, repetindo).
        """
        if self._current is None:
            return None
        if position_ms > RESTART_THRESHOLD_MS:
            return self._current.item
        position = self._order.index(self._current)
        if position > 0:
            self._current = self._order[position - 1]
        elif self.repeat is not RepeatMode.OFF:
            self._current = self._order[-1]
        return self._current.item

    # --- modos

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @shuffle.setter
    def shuffle(self, on: bool) -> None:
        """Ligar embaralha o resto, mantendo a faixa atual. Desligar volta à ordem da lista a
        partir da faixa atual.
        """
        if on == self._shuffle:
            return
        self._shuffle = on
        self._rebuild_order()

    def cycle_repeat(self) -> RepeatMode:
        """Desligado → repetir todas → repetir uma → desligado (o botão "Repetir")."""
        self.repeat = _NEXT_REPEAT[self.repeat]
        return self.repeat

    # --- detalhes

    def _rebuild_order(self) -> None:
        if not self._shuffle:
            self._order = list(self._entries)
            return
        others = [entry for entry in self._entries if entry is not self._current]
        self._rng.shuffle(others)
        self._order = ([self._current] if self._current else []) + others

    def _reshuffle(self, avoid_first: _Entry[T] | None = None) -> None:
        """Novo ciclo do aleatório. A que acabou de tocar não abre o ciclo seguinte (seria
        a mesma faixa duas vezes seguidas).
        """
        self._order = list(self._entries)
        self._rng.shuffle(self._order)
        if avoid_first is not None and len(self._order) > 1 and self._order[0] is avoid_first:
            self._order[0], self._order[1] = self._order[1], self._order[0]
