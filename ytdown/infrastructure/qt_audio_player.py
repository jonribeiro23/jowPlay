"""AudioPlayer com o QtMultimedia (QMediaPlayer + QAudioOutput), validado no spike JOW-9.

Um único QMediaPlayer serve todas as faixas: trocar de faixa troca a fonte dele, então nunca
há dois áudios tocando juntos. Os avisos do Qt chegam na thread da interface e são repassados
ao listener já traduzidos (estado, fim da faixa, mensagem de erro para o usuário).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QtAudio

from ytdown.application.ports import PlayerListener, PlayerState

_STATES = {
    QMediaPlayer.PlaybackState.StoppedState: PlayerState.STOPPED,
    QMediaPlayer.PlaybackState.PlayingState: PlayerState.PLAYING,
    QMediaPlayer.PlaybackState.PausedState: PlayerState.PAUSED,
}


class _Silent:
    def on_position(self, position_ms: int) -> None: ...

    def on_duration(self, duration_ms: int) -> None: ...

    def on_state(self, state: PlayerState) -> None: ...

    def on_finished(self) -> None: ...

    def on_error(self, message: str) -> None: ...


def missing_file_message(path: Path) -> str:
    return f"Não foi possível tocar \"{path.name}\": o arquivo não foi encontrado."


def error_message(path: Path | None, error: QMediaPlayer.Error, detail: str) -> str:
    name = f"\"{path.name}\"" if path else "o áudio"
    if error is QMediaPlayer.Error.AccessDeniedError:
        return f"Não foi possível tocar {name}: sem permissão para abrir o arquivo."
    if error in (QMediaPlayer.Error.FormatError, QMediaPlayer.Error.ResourceError):
        return f"Não foi possível tocar {name}: o arquivo está corrompido ou o formato não é suportado."
    return f"Não foi possível tocar {name}: {detail}" if detail else f"Não foi possível tocar {name}."


def perceived_to_linear(volume: int) -> float:
    """O controle de volume segue o ouvido (logarítmico); o QAudioOutput espera amplitude (linear)."""
    return QtAudio.convertVolume(volume / 100, QtAudio.VolumeScale.LogarithmicVolumeScale,
                                 QtAudio.VolumeScale.LinearVolumeScale)


class QtAudioPlayer:
    """Implementa AudioPlayer. Precisa de uma QApplication e deve ser usado na thread da interface."""

    def __init__(self, parent: QObject | None = None, volume: int = 80) -> None:
        self._player = QMediaPlayer(parent)
        self._output = QAudioOutput(parent)
        self._player.setAudioOutput(self._output)
        self._listener: PlayerListener = _Silent()
        self._path: Path | None = None
        self._volume = 0
        self.set_volume(volume)

        self._player.positionChanged.connect(lambda position: self._listener.on_position(position))
        self._player.durationChanged.connect(lambda duration: self._listener.on_duration(duration))
        self._player.playbackStateChanged.connect(lambda state: self._listener.on_state(_STATES[state]))
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)

    # --- AudioPlayer

    def set_listener(self, listener: PlayerListener) -> None:
        self._listener = listener

    def load(self, path: Path) -> None:
        self._player.stop()
        self._path = path
        if not path.is_file():
            # Sem isso, o Qt continuaria com a faixa anterior carregada.
            self._player.setSource(QUrl())
            self._listener.on_error(missing_file_message(path))
            return
        self._player.setSource(QUrl.fromLocalFile(str(path)))

    def play(self) -> None:
        if not self._player.source().isEmpty():
            self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def seek(self, position_ms: int) -> None:
        self._player.setPosition(max(0, position_ms))

    @property
    def state(self) -> PlayerState:
        return _STATES[self._player.playbackState()]

    @property
    def position_ms(self) -> int:
        return self._player.position()

    @property
    def duration_ms(self) -> int:
        return self._player.duration()

    @property
    def volume(self) -> int:
        return self._volume

    def set_volume(self, volume: int) -> None:
        self._volume = min(100, max(0, volume))
        self._output.setVolume(perceived_to_linear(self._volume))

    @property
    def muted(self) -> bool:
        return self._output.isMuted()

    def set_muted(self, muted: bool) -> None:
        self._output.setMuted(muted)

    # --- extras

    @property
    def source(self) -> Path | None:
        """O arquivo carregado no Qt (None se nenhum ou se o último não existia)."""
        url = self._player.source()
        return Path(url.toLocalFile()) if not url.isEmpty() else None

    def shutdown(self) -> None:
        """Para e solta o arquivo (ex.: ao fechar o app, para o Windows liberar o arquivo)."""
        self._player.stop()
        self._player.setSource(QUrl())

    # --- detalhes

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status is QMediaPlayer.MediaStatus.EndOfMedia:
            self._listener.on_finished()

    def _on_error(self, error: QMediaPlayer.Error, detail: str) -> None:
        if error is QMediaPlayer.Error.NoError:
            return
        self._player.stop()
        self._listener.on_error(error_message(self._path, error, detail))
