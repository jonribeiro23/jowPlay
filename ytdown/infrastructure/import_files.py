"""Varredura, SHA-256 e staging sem alterar os arquivos antigos."""
import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from ytdown.domain.errors import ExtractionCancelled

CHUNK_SIZE = 1024 * 1024


def checkpoint(cancel, tick):
    tick()
    if cancel.is_set():
        raise ExtractionCancelled()


class FileSystemImportFiles:
    def scan(self, folders, excluded, cancel, tick):
        excluded = excluded.resolve()
        found, seen, errors = [], set(), []
        def allowed(path):
            try:
                return not (path.is_symlink() or path.is_junction()
                            or path.resolve().is_relative_to(excluded))
            except OSError as exc:
                errors.append(f'{path}: {exc}')
                return False

        for folder in folders:
            checkpoint(cancel, tick)
            folder = Path(folder)
            if not allowed(folder):
                continue
            try:
                available = folder.is_dir()
            except OSError as exc:
                errors.append(f'{folder}: {exc}')
                continue
            if not available:
                errors.append(f'{folder}: pasta indisponível')
                continue
            def onerror(exc):
                errors.append(str(exc))
            for root, dirs, files in os.walk(folder, followlinks=False, onerror=onerror):
                checkpoint(cancel, tick)
                root = Path(root)
                if not allowed(root):
                    dirs[:] = []
                    continue
                kept = []
                for directory in dirs:
                    checkpoint(cancel, tick)
                    if allowed(root / directory):
                        kept.append(directory)
                dirs[:] = kept
                for name in files:
                    checkpoint(cancel, tick)
                    path = root/name
                    if path.suffix.lower() not in {'.mp3', '.m4a', '.flac', '.wav'} or not allowed(path):
                        continue
                    try:
                        key = path.resolve()
                    except OSError as exc:
                        errors.append(f'{path}: {exc}')
                        continue
                    if key not in seen:
                        seen.add(key)
                        found.append(path)
        return found, errors

    def fingerprint(self, path, cancel, tick):
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while True:
                checkpoint(cancel, tick)
                block = stream.read(CHUNK_SIZE)
                if not block:
                    return digest.hexdigest()
                digest.update(block)

    @contextmanager
    def staged(self, source, root, cancel, tick):
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.ytdown-import-', dir=root) as temporary:
            target = Path(temporary) / ('audio' + source.suffix.lower())
            with source.open('rb') as incoming, target.open('wb') as outgoing:
                while True:
                    checkpoint(cancel, tick)
                    block = incoming.read(CHUNK_SIZE)
                    if not block:
                        break
                    outgoing.write(block)
            checkpoint(cancel, tick)
            yield target
