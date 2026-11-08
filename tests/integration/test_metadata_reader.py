"""Lê etiquetas, duração e capa de arquivos de áudio reais, criados com o ffmpeg. Não usa a rede."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from mutagen.id3 import APIC, ID3

from ytdown.domain.errors import UnreadableAudio
from ytdown.domain.models import AudioFileInfo, AudioTags
from ytdown.infrastructure.covers import PillowCoverLoader
from ytdown.infrastructure.metadata_reader import MutagenMetadataReader
from ytdown.infrastructure.resources import asset
from ytdown.infrastructure.tags import MutagenTagWriter

FORMATS = ("mp3", "m4a", "flac", "wav")


def ffprobe_duration_ms(path: Path) -> float:
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(output)["format"]["duration"]) * 1000


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "precisa do ffmpeg e do ffprobe")
class MutagenMetadataReaderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.reader = MutagenMetadataReader()
        self.tags = AudioTags(
            title="Canção número 1 ação",
            cover=PillowCoverLoader(asset("default_cover.jpg")).load(None),
            artist="João & Conceição",
            album="Álbum de Verão",
            genre="MPB",
            year=2024,
            track_no=7,
            source_url="https://www.youtube.com/watch?v=jNQXAC9IVRw",
        )

    def make_audio(self, extension: str, seconds: float = 0.5, metadata: dict | None = None) -> Path:
        path = self.dir / f"a.{extension}"
        command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                   "-t", str(seconds)]
        for key, value in (metadata or {}).items():
            command += ["-metadata", f"{key}={value}"]
        subprocess.run([*command, str(path)], check=True)
        return path

    def test_reads_back_everything_the_writer_wrote(self):
        for extension in FORMATS:
            with self.subTest(extension):
                path = self.make_audio(extension)
                MutagenTagWriter().write(path, self.tags)
                info = self.reader.read(path)
                expected = AudioFileInfo(
                    duration_ms=info.duration_ms, title=self.tags.title, artist=self.tags.artist,
                    album=self.tags.album, genre=self.tags.genre, year=self.tags.year, track_no=self.tags.track_no,
                    source_url=self.tags.source_url, has_cover=True,
                )
                self.assertEqual(info, expected)
                self.assertEqual(self.reader.read_cover(path), self.tags.cover)

    def test_duration_is_accurate_to_one_second(self):
        for extension in FORMATS:
            with self.subTest(extension):
                path = self.make_audio(extension, seconds=3.5)
                duration = self.reader.read(path).duration_ms
                self.assertLess(abs(duration - ffprobe_duration_ms(path)), 1000)
                self.assertLess(abs(duration - 3500), 1000)

    def test_file_without_tags_gives_only_the_duration(self):
        for extension in FORMATS:
            with self.subTest(extension):
                path = self.make_audio(extension)
                info = self.reader.read(path)
                self.assertGreater(info.duration_ms, 0)
                self.assertEqual(info, AudioFileInfo(duration_ms=info.duration_ms))
                self.assertIsNone(self.reader.read_cover(path))

    def test_tags_written_by_other_tools(self):
        # O ffmpeg grava ID3v2.4, data completa e faixa no formato "nº/total".
        metadata = {"title": "Outra ferramenta", "artist": "Fulano", "album": "Disco", "genre": "Rock",
                    "date": "2019-05-01", "track": "3/12"}
        for extension in ("mp3", "m4a", "flac"):
            with self.subTest(extension):
                info = self.reader.read(self.make_audio(extension, metadata=metadata))
                self.assertEqual(
                    (info.title, info.artist, info.album, info.genre, info.year, info.track_no),
                    ("Outra ferramenta", "Fulano", "Disco", "Rock", 2019, 3),
                )

    def test_front_cover_is_preferred_over_other_pictures(self):
        path = self.make_audio("mp3")
        id3 = ID3()
        id3.add(APIC(encoding=3, mime="image/jpeg", type=0, desc="Outra", data=b"outra imagem"))
        id3.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Frente", data=b"capa da frente"))
        id3.save(path)
        self.assertEqual(self.reader.read_cover(path), b"capa da frente")

    def test_blank_tags_count_as_missing(self):
        path = self.make_audio("flac", metadata={"title": "   ", "date": "0"})
        info = self.reader.read(path)
        self.assertEqual((info.title, info.year), (None, None))

    def test_broken_missing_and_unsupported_files_give_a_clear_error(self):
        broken = []
        for extension in FORMATS:
            path = self.dir / f"quebrado.{extension}"
            path.write_bytes(b"isto nao e audio" * 10)
            broken.append(path)
        for path in (*broken, self.dir / "nao-existe.mp3", self.make_audio("wav").with_suffix(".ogg")):
            with self.subTest(path.name), self.assertRaises(UnreadableAudio) as caught:
                self.reader.read(path)
            self.assertIn(path.name, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
