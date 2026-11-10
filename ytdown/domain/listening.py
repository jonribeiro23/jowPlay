"""Contagem de tempo efetivamente ouvido em uma execução da faixa."""


class Listening:
    def __init__(self, duration_ms: int = 0):
        self.duration_ms = max(0, duration_ms)
        self.heard_ms = 0.0
        self.counted = False

    def advance(self, position_delta_ms: int, elapsed_ms: float) -> None:
        self.heard_ms += max(0, min(position_delta_ms, elapsed_ms))

    @property
    def qualifies(self) -> bool:
        return (not self.counted and self.duration_ms > 0 and
                self.heard_ms >= min(self.duration_ms / 2, 240_000))
