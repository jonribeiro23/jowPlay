"""Importação explícita de extrações antigas; nenhuma dependência de Qt ou I/O concreto."""
from dataclasses import dataclass, field
from datetime import datetime
from threading import Event

from ytdown.application.ports import ImportFiles, LibraryStorage, MetadataReader, TrackRepository
from ytdown.domain.errors import ExtractionCancelled
from ytdown.domain.library import Track
from ytdown.domain.library_paths import library_path
from ytdown.domain.urls import canonical_video_url


@dataclass
class ImportResult:
    imported: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


class ImportAudios:
    def __init__(self, storage: LibraryStorage, tracks: TrackRepository,
                 reader: MetadataReader, files: ImportFiles):
        self.storage, self.tracks, self.reader, self.files = storage, tracks, reader, files

    def __call__(self, folders, cancel=None, on_progress=lambda phase, done, total: None):
        cancel = cancel if cancel is not None else Event()
        result = ImportResult()
        def check():
            if cancel.is_set():
                raise ExtractionCancelled()
        def tick(phase, done=0, total=0):
            on_progress(phase, done, total)
            check()
        def url_key(url):
            return canonical_video_url(url) or url
        try:
            hashes, urls = set(), set()
            existing = self.tracks.list_tracks()
            for index, track in enumerate(existing):
                tick('Indexando biblioteca', index, len(existing))
                if track.source_url:
                    urls.add(url_key(track.source_url))
                path = self.storage.absolute(track.rel_path)
                try:
                    hashes.add(self.files.fingerprint(path, cancel, lambda: tick('Verificando duplicatas na biblioteca', index, len(existing))))
                except FileNotFoundError:
                    pass  # Faixas ausentes ainda participam da deduplicação por URL.
                except OSError as exc:
                    result.errors.append(f'{path}: {exc}')
                    return result  # Não importar sem poder verificar duplicatas existentes.
            paths, errors = self.files.scan(folders, self.storage.root, cancel, lambda: tick('Procurando áudios'))
            result.errors.extend(errors)
            for index, source in enumerate(paths):
                tick('Importando', index, len(paths))
                try:
                    with self.files.staged(source, self.storage.root, cancel, lambda: tick('Copiando ' + source.name, index, len(paths))) as staged:
                        info = self.reader.read(staged)  # Corrupção é erro, nunca duração zero.
                        check()
                        digest = self.files.fingerprint(staged, cancel, lambda: tick('Verificando duplicatas ' + source.name, index, len(paths)))
                        url = url_key(info.source_url) if info.source_url else None
                        if digest in hashes or (url and url in urls):
                            result.duplicates += 1
                        else:
                            wanted = library_path(info.artist or '', info.album or '', info.title or source.stem,
                                                  info.track_no, source.suffix.lower(), self.storage.max_relative_length())
                            check()
                            placed = self.storage.place(staged, wanted)
                            try:
                                check()
                                self.tracks.add(Track(rel_path=placed, title=info.title or source.stem,
                                    artist=info.artist or '', album=info.album or '', genre=info.genre or '',
                                    year=info.year, track_no=info.track_no, duration_ms=info.duration_ms,
                                    source_url=url, added_at=datetime.now()))
                            except Exception as original:
                                try:
                                    self.storage.discard(placed)
                                except Exception as cleanup:
                                    result.errors.append(
                                        f'{source}: {original or type(original).__name__}; '
                                        f'falha ao limpar destino residual {self.storage.absolute(placed)}: {cleanup}')
                                raise
                            result.imported += 1
                            hashes.add(digest)
                            if url:
                                urls.add(url)
                except ExtractionCancelled:
                    raise
                except Exception as exc:
                    result.errors.append(f'{source}: {exc}')
                tick('Importando', index + 1, len(paths))
        except ExtractionCancelled:
            result.cancelled = True
        return result
