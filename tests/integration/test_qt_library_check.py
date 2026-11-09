"""A checagem de abertura roda fora da interface e atualiza a lista ao terminar."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tests.fakes import FakeAudioPlayer, FakeCovers, FakeDownloader, FakeTags
from tests.qt_support import dispose, qt_app, wait_until
from ytdown.application.extraction import ExtractAudio, ExtractBatch
from ytdown.application.playback import Playback
from ytdown.bootstrap import build_library, build_main_window, start_library_check
from ytdown.domain.library import Track
from ytdown.presentation.qt.pages import PageId
from ytdown.presentation.qt.send_dialog import PhoneSharing


class LibraryCheckQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_startup_check_is_asynchronous_and_refreshes_songs(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        library = build_library(root / "index.db", root / "settings.json", root / "music")
        self.addCleanup(library.close)
        library.storage.root.mkdir()
        track = library.tracks.add(Track("missing.mp3", "Missing", datetime.now()))
        batch = ExtractBatch(ExtractAudio(FakeDownloader(), FakeCovers(), FakeTags()), FakeCovers())
        window = build_main_window(library, Playback(FakeAudioPlayer(), library.storage, tracks=library.tracks),
                                   batch, PhoneSharing(lambda _: None))
        self.addCleanup(dispose, window)
        start_library_check(window, library)
        self.assertTrue(wait_until(lambda: not window.library_check.is_working()))
        self.assertTrue(wait_until(lambda: window.page(PageId.SONGS).model.tracks[0].missing))
        self.assertTrue(library.tracks.get(track.id).missing)


if __name__ == "__main__":
    unittest.main()
