"""Da extração à biblioteca, com as peças reais: etiquetas (mutagen), capa (Pillow), pasta
gerenciada, SQLite e leitura da duração. Só o download é simulado (um MP3 real, gerado pelo
ffmpeg), para o teste não depender da rede.
"""

import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from mutagen.id3 import ID3

from ytdown.application.extraction import ExtractAudio, ExtractBatch
from ytdown.application.library import RegisterExtractedTrack
from ytdown.application.ports import DownloadedAudio
from ytdown.domain.library import DuplicatePolicy, TrackQuery
from ytdown.domain.models import AUDIO_FORMATS, AudioMetadata
from ytdown.domain.urls import canonical_video_url
from ytdown.infrastructure.covers import PillowCoverLoader
from ytdown.infrastructure.library_storage import FileSystemLibraryStorage
from ytdown.infrastructure.metadata_reader import MutagenMetadataReader
from ytdown.infrastructure.resources import asset
from ytdown.infrastructure.sqlite_library import SqliteTrackRepository
from ytdown.infrastructure.tags import MutagenTagWriter

MP3 = AUDIO_FORMATS[0]
VIDEOS = {
    "https://youtu.be/aaaaaaaaaaa": "Primeira música",
    "https://www.youtube.com/watch?v=bbbbbbbbbbb": "Segunda música",
}


class SampleDownloader:
    """Copia um MP3 real para a pasta de trabalho, como o yt-dlp faria."""

    def __init__(self, sample: Path) -> None:
        self.sample = sample

    def download(self, url, work_dir, audio_format, on_progress, cancel):
        title = VIDEOS[url]
        path = work_dir / f"{title}.mp3"
        shutil.copy(self.sample, path)
        return DownloadedAudio(path, title, canonical_video_url(url))


@unittest.skipUnless(shutil.which("ffmpeg"), "precisa do ffmpeg")
class ExtractToLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_dir = tempfile.TemporaryDirectory()
        cls.sample = Path(cls.sample_dir.name) / "amostra.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                        "-t", "1", str(cls.sample)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.sample_dir.cleanup()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "Biblioteca"
        self.trashed = []
        storage = FileSystemLibraryStorage(self.root, trash_file=self.fake_trash)
        self.tracks = SqliteTrackRepository(Path(temp.name) / "library.db")
        self.addCleanup(self.tracks.close)
        self.register = RegisterExtractedTrack(storage, self.tracks, MutagenMetadataReader())
        covers = PillowCoverLoader(default_cover=asset("default_cover.jpg"))
        self.batch = ExtractBatch(ExtractAudio(SampleDownloader(self.sample), covers, MutagenTagWriter()), covers)

    def fake_trash(self, path):
        self.trashed.append(path)
        path.unlink()

    def extract(self, policy=DuplicatePolicy.KEEP_BOTH):
        return self.batch(
            list(VIDEOS), self.register.destination(policy), MP3,
            AudioMetadata(artist="Banda", album="Disco", genre="Rock", year=2024),
            on_progress=lambda index, progress: None, on_result=lambda index, result: None,
            cancel=threading.Event(),
        )

    def test_a_queue_of_two_videos_ends_up_in_the_database_and_in_artist_album(self):
        results = self.extract()

        expected = [self.root / "Banda" / "Disco" / f"{title}.mp3" for title in VIDEOS.values()]
        self.assertEqual([r.error for r in results], [None, None])
        self.assertEqual([r.path for r in results], expected)
        self.assertTrue(all(path.exists() for path in expected))

        tracks = self.tracks.list_tracks(TrackQuery())
        self.assertEqual(sorted(t.title for t in tracks), sorted(VIDEOS.values()))
        for track in tracks:
            with self.subTest(track.title):
                self.assertEqual((track.artist, track.album, track.genre, track.year), ("Banda", "Disco", "Rock", 2024))
                self.assertEqual(track.rel_path, f"Banda/Disco/{track.title}.mp3")
                self.assertGreater(track.duration_ms, 900)
                self.assertTrue(track.source_url.startswith("https://www.youtube.com/watch?v="))
                # A URL de origem também está no arquivo (as etiquetas são a fonte da verdade).
                frame = ID3(self.root / "Banda" / "Disco" / f"{track.title}.mp3").getall("WOAS")[0]
                self.assertEqual(frame.url, track.source_url)
        self.assertEqual([a.name for a in self.tracks.artists()], ["Banda"])

    def test_extracting_again_finds_the_duplicates_and_replace_keeps_one_of_each(self):
        self.extract()
        first_ids = sorted(t.id for t in self.tracks.list_tracks())
        self.assertEqual(len(self.register.find_duplicates(list(VIDEOS))), 2)

        results = self.extract(DuplicatePolicy.REPLACE)

        self.assertEqual(sorted(t.id for t in self.tracks.list_tracks()), first_ids)
        self.assertEqual(len(self.trashed), 2)  # Os arquivos antigos foram para a "Lixeira".
        self.assertEqual(sorted(p.name for p in (self.root / "Banda" / "Disco").iterdir()),
                         sorted(f"{title}.mp3" for title in VIDEOS.values()))
        self.assertTrue(all(r.path.exists() for r in results))

    def test_keep_both_adds_copies_beside_the_originals(self):
        self.extract()
        self.extract(DuplicatePolicy.KEEP_BOTH)
        self.assertEqual(len(self.tracks.list_tracks()), 4)
        self.assertEqual(len(list((self.root / "Banda" / "Disco").iterdir())), 4)


if __name__ == "__main__":
    unittest.main()
