"""Grava metadados em arquivos de áudio reais, criados com o ffmpeg. Não usa a rede."""

import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE
from PIL import Image

import tags

TITLE = "Canção número 1 ação"
AUTHOR = "João & Conceição"


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
class WriteTagsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.cover = tags.load_cover(None)

    def make_audio(self, extension: str) -> Path:
        path = self.dir / f"a.{extension}"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100", "-t", "0.2", str(path)],
            check=True,
        )
        return path

    def test_every_format_keeps_title_author_and_cover(self):
        for extension in ("mp3", "m4a", "flac", "wav"):
            with self.subTest(extension):
                path = self.make_audio(extension)
                tags.write_tags(path, TITLE, AUTHOR, self.cover)
                self.assertEqual(read_tags(path), (TITLE, AUTHOR, self.cover))

    def test_empty_author_removes_previous_author(self):
        for extension in ("mp3", "m4a", "flac", "wav"):
            with self.subTest(extension):
                path = self.make_audio(extension)
                tags.write_tags(path, TITLE, AUTHOR, self.cover)
                tags.write_tags(path, TITLE, "", self.cover)
                self.assertIsNone(read_tags(path)[1])


class LoadCoverTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)

    def load(self, image: Image.Image, name: str = "capa.png") -> Image.Image:
        path = self.dir / name
        image.save(path)
        return Image.open(io.BytesIO(tags.load_cover(path)))

    def test_default_cover_is_a_jpeg(self):
        self.assertEqual(Image.open(io.BytesIO(tags.load_cover(None))).format, "JPEG")

    def test_large_image_shrinks_and_keeps_proportion(self):
        cover = self.load(Image.new("RGB", (4000, 2000), "red"))
        self.assertEqual(cover.size, (1000, 500))

    def test_small_image_is_not_enlarged(self):
        self.assertEqual(self.load(Image.new("RGB", (300, 200), "red")).size, (300, 200))

    def test_transparency_becomes_white(self):
        cover = self.load(Image.new("RGBA", (50, 50), (255, 0, 0, 0)))
        self.assertTrue(all(channel > 250 for channel in cover.getpixel((25, 25))))

    def test_other_image_formats_are_accepted(self):
        for name in ("capa.webp", "capa.bmp", "capa.gif"):
            with self.subTest(name):
                self.assertEqual(self.load(Image.new("RGB", (40, 40), "blue"), name).format, "JPEG")

    def test_rejects_files_that_are_not_images(self):
        path = self.dir / "texto.png"
        path.write_text("isto não é uma imagem", encoding="utf-8")
        with self.assertRaises(tags.InvalidCover):
            tags.load_cover(path)

    def test_rejects_missing_file(self):
        with self.assertRaises(tags.InvalidCover):
            tags.load_cover(self.dir / "nao-existe.png")


if __name__ == "__main__":
    unittest.main()
