import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ytdown.domain.errors import InvalidCover
from ytdown.infrastructure.covers import MAX_COVER_SIZE, PillowCoverLoader
from ytdown.infrastructure.resources import asset


class PillowCoverLoaderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.loader = PillowCoverLoader(asset("default_cover.jpg"))

    def load(self, image: Image.Image, name: str = "capa.png") -> Image.Image:
        path = self.dir / name
        image.save(path)
        return Image.open(io.BytesIO(self.loader.load(path)))

    def test_default_cover_is_a_jpeg(self):
        self.assertEqual(Image.open(io.BytesIO(self.loader.load(None))).format, "JPEG")

    def test_large_image_shrinks_and_keeps_proportion(self):
        cover = self.load(Image.new("RGB", (4 * MAX_COVER_SIZE, 2 * MAX_COVER_SIZE), "red"))
        self.assertEqual(cover.size, (MAX_COVER_SIZE, MAX_COVER_SIZE // 2))

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
        with self.assertRaises(InvalidCover):
            self.loader.load(path)

    def test_rejects_missing_file(self):
        with self.assertRaises(InvalidCover):
            self.loader.load(self.dir / "nao-existe.png")


if __name__ == "__main__":
    unittest.main()
