"""Grava metadados em arquivos de áudio reais, criados com o ffmpeg. Não usa a rede."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

from ytdown.domain.errors import ExtractionError
from ytdown.infrastructure.covers import PillowCoverLoader
from ytdown.infrastructure.resources import asset
from ytdown.infrastructure.tags import MutagenTagWriter

TITLE = "Canção número 1 ação"
AUTHOR = "João & Conceição"
FORMATS = ("mp3", "m4a", "flac", "wav")


def read_tags(path: Path) -> tuple[str, str | None, bytes]:
    """Devolve (nome, autor, capa) lendo o arquivo de volta."""
    suffix = path.suffix
    if suffix in (".mp3", ".wav"):
        id3 = ID3(path) if suffix == ".mp3" else WAVE(path).tags
        artist = id3.get("TPE1")
        return id3["TIT2"].text[0], artist.text[0] if artist else None, id3.getall("APIC")[0].data
    if suffix == ".m4a":
        mp4 = MP4(path)
        return mp4["\xa9nam"][0], mp4.get("\xa9ART", [None])[0], bytes(mp4["covr"][0])
    flac = FLAC(path)
    return flac["title"][0], flac.get("artist", [None])[0], flac.pictures[0].data


@unittest.skipUnless(shutil.which("ffmpeg"), "precisa do ffmpeg")
class MutagenTagWriterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.cover = PillowCoverLoader(asset("default_cover.jpg")).load(None)
        self.writer = MutagenTagWriter()

    def make_audio(self, extension: str) -> Path:
        path = self.dir / f"a.{extension}"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100", "-t", "0.2", str(path)], check=True
        )
        return path

    def test_every_format_keeps_title_author_and_cover(self):
        for extension in FORMATS:
            with self.subTest(extension):
                path = self.make_audio(extension)
                self.writer.write(path, TITLE, AUTHOR, self.cover)
                self.assertEqual(read_tags(path), (TITLE, AUTHOR, self.cover))

    def test_empty_author_removes_previous_author(self):
        for extension in FORMATS:
            with self.subTest(extension):
                path = self.make_audio(extension)
                self.writer.write(path, TITLE, AUTHOR, self.cover)
                self.writer.write(path, TITLE, "", self.cover)
                self.assertIsNone(read_tags(path)[1])

    def test_unsupported_or_broken_files_give_a_readable_error(self):
        # FLAC tem cabeçalho obrigatório; um MP3 sem etiqueta apenas recebe uma nova.
        broken = self.dir / "quebrado.flac"
        broken.write_bytes(b"isto nao e audio")
        for path in (self.dir / "a.ogg", broken):
            with self.subTest(path.name), self.assertRaises(ExtractionError):
                self.writer.write(path, TITLE, AUTHOR, self.cover)


if __name__ == "__main__":
    unittest.main()
