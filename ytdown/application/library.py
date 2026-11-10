"""Casos de uso da biblioteca."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from threading import Event
import shutil
import tempfile

from ytdown.application.ports import LibraryStorage, MetadataReader, Settings, TrackRepository, ThumbnailCache
from ytdown.domain.errors import ExtractionError, LibraryError, UnreadableAudio
from ytdown.domain.library import UNKNOWN_GENRE, DuplicatePolicy, Track
from ytdown.domain.library_paths import library_path
from ytdown.domain.models import AudioTags
from ytdown.domain.text import search_key
from ytdown.domain.urls import canonical_video_url

LIBRARY_FOLDER_KEY = "library_folder"


class DeleteTracks:
    """Envia cada faixa à Lixeira e confirma o índice individualmente."""

    def __init__(self, storage, tracks, playback):
        self.storage, self.tracks, self.playback = storage, tracks, playback

    def __call__(self, ids):
        removed, errors = set(), []
        for track_id in dict.fromkeys(ids):
            track = self.tracks.get(track_id)
            if track is None:
                continue
            try:
                path = self.storage.absolute(track.rel_path)
                if not self.storage.is_available() or not self.storage.exists(track.rel_path):
                    raise LibraryError("Arquivo ou pasta da biblioteca indisponível")
                temp = Path(tempfile.mkdtemp(prefix="ytdown-delete-"))
                backup = temp / path.name
                safe_to_clean = True
                try:
                    shutil.copy2(path, backup)
                    current = self.playback.current
                    displaced = ([item for item in self.playback.queue if item.id == track_id]
                                 if current is not None and current.id == track_id else [])
                    if displaced:
                        self.playback.remove_tracks({track_id})
                    try:
                        self.tracks.remove_with_file(track_id, lambda: self.storage.trash(track.rel_path))
                    except Exception as exc:
                        if not path.exists():
                            try:
                                path.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(backup, path)
                            except OSError as restore_error:
                                safe_to_clean = False
                                raise LibraryError(f"{exc}; cópia de recuperação em {backup}: {restore_error}") from exc
                        if displaced:
                            self.playback.append(displaced)
                        raise
                    self.playback.remove_tracks({track_id})
                finally:
                    if safe_to_clean:
                        shutil.rmtree(temp, ignore_errors=True)
                removed.add(track_id)
            except Exception as exc:
                errors.append((track, str(exc)))
        return removed, errors


@dataclass(frozen=True)
class CheckLibraryResult:
    """Resumo da verificação para a interface decidir o que comunicar."""

    indexed: int
    checked: int = 0
    changed: int = 0
    errors: int = 0
    root_available: bool = True
    cancelled: bool = False


class CheckLibrary:
    """Sincroniza ``Track.missing`` com os arquivos da raiz gerenciada.

    Uma raiz ausente (inclusive antes da primeira extração) ou uma unidade
    inacessível não demonstra que todo arquivo do índice desapareceu. Nesse caso
    esta operação não toca nas faixas.
    """

    def __init__(self, storage: LibraryStorage, tracks: TrackRepository) -> None:
        self._storage = storage
        self._tracks = tracks

    def __call__(self, cancel: Event | None = None) -> CheckLibraryResult:
        cancel = cancel or Event()
        indexed = self._tracks.list_tracks()
        if cancel.is_set():
            return CheckLibraryResult(indexed=len(indexed), cancelled=True)
        if not self._storage.is_available():
            return CheckLibraryResult(indexed=len(indexed), root_available=False)

        checked = changed = errors = 0
        for track in indexed:
            if cancel.is_set():
                return CheckLibraryResult(
                    indexed=len(indexed), checked=checked, changed=changed,
                    errors=errors, cancelled=True,
                )
            try:
                missing = not self._storage.exists(track.rel_path)
            except (LibraryError, OSError):
                # Um erro pontual é inconclusivo; conserva o último estado.
                errors += 1
                continue
            checked += 1
            if track.missing != missing:
                self._tracks.update(replace(track, missing=missing))
                changed += 1
        return CheckLibraryResult(indexed=len(indexed), checked=checked, changed=changed, errors=errors)


class RemoveUnavailableTracks:
    """Remove do índice somente faixas ainda indisponíveis, sem tocar no disco."""

    def __init__(self, storage: LibraryStorage, tracks: TrackRepository) -> None:
        self._storage = storage
        self._tracks = tracks

    def __call__(self) -> set[int]:
        if not self._storage.is_available():
            return set()
        removed: set[int] = set()
        for track in self._tracks.list_tracks():
            if not track.missing or track.id is None:
                continue
            try:
                present = self._storage.exists(track.rel_path)
            except (LibraryError, OSError):
                continue
            if present:
                self._tracks.update(replace(track, missing=False))
            else:
                self._tracks.remove(track.id)
                removed.add(track.id)
        return removed


def known_genres(tracks: TrackRepository) -> list[str]:
    """Os gêneros que já existem na biblioteca, na ordem da navegação, para sugerir ao digitar.
    Grafias que só mudam em maiúsculas ou acentos ("Rock" e "rock") aparecem uma vez só.
    """
    seen: set[str] = set()
    names = []
    for genre in tracks.genres():
        key = search_key(genre.name)
        if genre.name != UNKNOWN_GENRE and key not in seen:
            seen.add(key)
            names.append(genre.name)
    return names


def library_folder(settings: Settings, default: Path) -> Path:
    """A pasta da biblioteca escolhida pelo usuário, ou `default` se ele nunca escolheu."""
    chosen = settings.get(LIBRARY_FOLDER_KEY)
    return Path(chosen) if chosen else default


class ChangeLibraryFolder:
    """Move a biblioteca inteira para outra pasta, mantendo o índice coerente."""

    def __init__(self, storage: LibraryStorage, tracks: TrackRepository, settings: Settings) -> None:
        self._storage = storage
        self._tracks = tracks
        self._settings = settings

    def __call__(self, new_root: Path, on_progress: Callable[[int, int], None] = lambda done, total: None) -> None:
        """Falha com LibraryError; nesse caso, nada muda (nem arquivos, nem índice, nem configuração)."""
        renamed = self._storage.relocate(new_root, on_progress)
        # Só arquivos que colidiram com algo já existente na pasta nova mudam de nome.
        for old_path, new_path in renamed.items():
            track = self._tracks.find_by_path(old_path)
            if track:
                self._tracks.update(replace(track, rel_path=new_path))
        self._settings.set(LIBRARY_FOLDER_KEY, str(new_root))


class RegisterExtractedTrack:
    """Coloca um áudio recém-extraído (já com as etiquetas) em `Artista/Álbum/NN - Título.ext`
    na pasta da biblioteca e cria a faixa no índice, com a URL de origem.

    Se o índice recusar a faixa, o arquivo colocado é apagado: nada fica órfão na pasta.
    """

    def __init__(
        self,
        storage: LibraryStorage,
        tracks: TrackRepository,
        reader: MetadataReader,
        clock: Callable[[], datetime] = datetime.now,
        thumbnails: ThumbnailCache | None = None,
    ) -> None:
        self._storage = storage
        self._tracks = tracks
        self._reader = reader
        self._clock = clock
        self._thumbnails = thumbnails

    @property
    def folder(self) -> Path:
        return self._storage.root

    def find_duplicates(self, urls: list[str]) -> list[tuple[str, Track]]:
        """As URLs cujo vídeo já está na biblioteca, com a faixa existente. Funciona antes de
        baixar, para perguntar ao usuário o que fazer uma única vez.
        """
        found = []
        for url in urls:
            canonical = canonical_video_url(url)
            track = self._tracks.find_by_source_url(canonical) if canonical else None
            if track:
                found.append((url, track))
        return found

    def destination(self, on_duplicate: DuplicatePolicy = DuplicatePolicy.KEEP_BOTH) -> LibraryDestination:
        """Destino para a extração (ExtractAudio/ExtractBatch) que registra cada áudio na biblioteca."""
        return LibraryDestination(self, on_duplicate)

    def __call__(
        self, file: Path, tags: AudioTags, on_duplicate: DuplicatePolicy = DuplicatePolicy.KEEP_BOTH
    ) -> Track:
        """Falha com LibraryError; nesse caso, a biblioteca fica como estava."""
        duration_ms = self._duration_ms(file)
        wanted = library_path(tags.artist, tags.album, tags.title, tags.track_no, file.suffix,
                              self._storage.max_relative_length())
        existing = None
        if on_duplicate is DuplicatePolicy.REPLACE and tags.source_url:
            existing = self._tracks.find_by_source_url(tags.source_url)

        placed = self._storage.place(file, wanted)
        fields = dict(
            rel_path=placed, title=tags.title, artist=tags.artist, album=tags.album, genre=tags.genre,
            year=tags.year, track_no=tags.track_no, duration_ms=duration_ms, source_url=tags.source_url,
            missing=False,
        )
        try:
            if existing:
                # Mesma faixa, arquivo novo: id, data de inclusão e reproduções continuam.
                track = replace(existing, **fields)
                self._tracks.update(track)
            else:
                track = self._tracks.add(Track(added_at=self._clock(), **fields))
        except Exception as exc:
            self._undo_place(placed)
            raise LibraryError(f"Não foi possível registrar {placed} na biblioteca: {exc}") from exc

        if existing:
            track = self._retire_old_file(existing, track, wanted)
        if self._thumbnails:
            self._thumbnails.request(self._storage.absolute(track.rel_path))
        return track

    def _duration_ms(self, file: Path) -> int:
        try:
            return self._reader.read(file).duration_ms
        except UnreadableAudio:
            return 0  # A faixa entra mesmo assim; a duração aparece como 0:00.

    def _undo_place(self, placed: str) -> None:
        try:
            self._storage.discard(placed)
        except LibraryError:
            pass  # Melhor esforço: o erro do registro é o que importa para o usuário.

    def _retire_old_file(self, old: Track, track: Track, wanted: str) -> Track:
        """Ao substituir: manda o arquivo antigo para a Lixeira e, se o novo ganhou " (1)" porque
        o antigo ocupava o nome, devolve a ele o nome certo. Falhas aqui não desfazem a extração.
        """
        if old.rel_path != track.rel_path:
            try:
                if self._storage.exists(old.rel_path):
                    self._storage.trash(old.rel_path)
            except LibraryError:
                return track  # O arquivo antigo fica na pasta; a faixa já usa o novo.
        if track.rel_path == wanted or self._storage.exists(wanted):
            return track
        try:
            moved = self._storage.move(track.rel_path, wanted)
        except LibraryError:
            return track
        renamed = replace(track, rel_path=moved)
        try:
            self._tracks.update(renamed)
        except Exception:
            try:
                self._storage.move(moved, track.rel_path)  # Arquivo e índice precisam concordar.
            except LibraryError:
                pass
            return track
        return renamed

    def path_of(self, track: Track) -> Path:
        return self._storage.absolute(track.rel_path)


class LibraryDestination:
    """AudioDestination da extração: cada áudio salvo entra na biblioteca."""

    def __init__(self, register: RegisterExtractedTrack, on_duplicate: DuplicatePolicy) -> None:
        self._register = register
        self.on_duplicate = on_duplicate

    def save(self, file: Path, tags: AudioTags) -> Path:
        try:
            track = self._register(file, tags, self.on_duplicate)
        except LibraryError as exc:
            raise ExtractionError(str(exc)) from exc
        return self._register.path_of(track)
