"""Liga compartilhamentos à identidade persistente de faixas da biblioteca."""
from pathlib import Path

from ytdown.domain.errors import LibraryError


class LibraryShareResolver:
    def __init__(self, tracks, storage, devices):
        self.tracks, self.storage, self.devices = tracks, storage, devices

    def identify(self, path: Path) -> str | None:
        try:
            relative = path.resolve().relative_to(self.storage.root.resolve()).as_posix()
            if self.storage.absolute(relative).resolve() != path.resolve():
                return None
        except (ValueError, OSError, LibraryError):
            return None
        share_id = self.tracks.shared_track_id(relative, self.devices.existing_shared_id(path))
        if share_id:
            self.devices.forget_shared_id(path)
        return share_id

    def resolve(self, share_id: str) -> Path | None:
        track = self.tracks.find_by_shared_id(share_id)
        if track is None:
            return None
        try:
            return self.storage.absolute(track.rel_path)
        except LibraryError:
            return None
