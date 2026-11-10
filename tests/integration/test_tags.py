"""Grava etiquetas em arquivos de áudio reais, criados com o ffmpeg, e as lê de volta
com o mutagen, de forma independente do gravador. Não usa a rede.
"""

import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from mutagen.flac import FLAC
from mutagen.id3 import APIC, ID3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

from ytdown.domain.errors import ExtractionError
from ytdown.domain.models import AudioTags
from ytdown.infrastructure.covers import PillowCoverLoader
from ytdown.infrastructure.resources import asset
from ytdown.infrastructure.tags import MP4_SOURCE_KEY, VORBIS_SOURCE_KEY, MutagenTagWriter

FORMATS = ("mp3", "m4a", "flac", "wav")
FIELDS = ("title", "artist", "album", "genre", "year", "track_no", "source_url", "cover")


def read_tags(path: Path) -> dict:
    """Lê de volta todos os campos que o ytDown grava; campo ausente vira None."""
    if path.suffix in (".mp3", ".wav"):
        id3 = ID3(path) if path.suffix == ".mp3" else WAVE(path).tags

        def text(frame):
            return str(id3[frame].text[0]) if frame in id3 else None

        woas = id3.getall("WOAS")
        year = text("TDRC")  # O mutagen converte o TYER gravado em v2.3 para TDRC ao ler.
        track = text("TRCK")
        return {
            "title": text("TIT2"), "artist": text("TPE1"), "album": text("TALB"), "genre": text("TCON"),
            "year": int(year) if year else None, "track_no": int(track) if track else None,
            "source_url": woas[0].url if woas else None, "cover": id3.getall("APIC")[0].data,
            "id3_version": id3.version,
        }
    if path.suffix == ".m4a":
        mp4 = MP4(path).tags

        def first(key):
            return mp4[key][0] if key in mp4 else None

        return {
            "title": first("\xa9nam"), "artist": first("\xa9ART"), "album": first("\xa9alb"),
            "genre": first("\xa9gen"), "year": int(first("\xa9day")) if first("\xa9day") else None,
            "track_no": first("trkn")[0] if first("trkn") else None,
            "source_url": bytes(first(MP4_SOURCE_KEY)).decode() if first(MP4_SOURCE_KEY) else None,
            "cover": bytes(first("covr")),
        }
    flac = FLAC(path)

    def vorbis(key):
        return flac[key][0] if key in flac else None

    return {
        "title": vorbis("title"), "artist": vorbis("artist"), "album": vorbis("album"), "genre": vorbis("genre"),
        "year": int(vorbis("date")) if vorbis("date") else None,
        "track_no": int(vorbis("tracknumber")) if vorbis("tracknumber") else None,
        "source_url": vorbis(VORBIS_SOURCE_KEY), "cover": flac.pictures[0].data,
    }


@unittest.skipUnless(shutil.which("ffmpeg"), "precisa do ffmpeg")
class MutagenTagWriterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.full = AudioTags(
            title="Canção número 1 ação",
            cover=PillowCoverLoader(asset("default_cover.jpg")).load(None),
            artist="João & Conceição",
            album="Álbum de Verão",
            genre="Música Popular Brasileira",
            year=2024,
            track_no=7,
            source_url="https://www.youtube.com/watch?v=jNQXAC9IVRw",
        )
        self.writer = MutagenTagWriter()

    def make_audio(self, extension: str) -> Path:
        path = self.dir / f"a.{extension}"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100", "-t", "0.2", str(path)], check=True
        )
        return path

    def assert_tags(self, path: Path, expected: AudioTags):
        found = read_tags(path)
        self.assertEqual({f: found[f] for f in FIELDS}, {f: getattr(expected, f) or None for f in FIELDS})

    def test_every_format_keeps_every_field(self):
        for extension in FORMATS:
            with self.subTest(extension):
                path = self.make_audio(extension)
                self.writer.write(path, self.full)
                self.assert_tags(path, self.full)

    def test_only_title_and_cover_are_required(self):
        minimal = AudioTags(title="Só o nome", cover=self.full.cover)
        for extension in FORMATS:
            with self.subTest(extension):
                path = self.make_audio(extension)
                self.writer.write(path, minimal)
                self.assert_tags(path, minimal)

    def test_empty_fields_remove_previous_values(self):
        cleared = replace(self.full, artist="", album="", genre="", year=None, track_no=None, source_url=None)
        for extension in FORMATS:
            with self.subTest(extension):
                path = self.make_audio(extension)
                self.writer.write(path, self.full)
                self.writer.write(path, cleared)
                self.assert_tags(path, cleared)

    def test_selective_update_preserves_other_fields_and_source(self):
        for extension in FORMATS:
            with self.subTest(extension=extension):
                path = self.make_audio(extension)
                self.writer.write(path, self.full)
                self.writer.update(path, {"artist": "Outro", "year": None})
                self.assert_tags(path, replace(self.full, artist="Outro", year=None))

    def test_selective_m4a_track_number_keeps_total(self):
        path = self.make_audio("m4a")
        self.writer.write(path, self.full)
        audio = MP4(path)
        audio.tags["trkn"] = [(7, 12)]
        audio.save()
        self.writer.update(path, {"track_no": 8})
        self.assertEqual(MP4(path).tags["trkn"], [(8, 12)])
        self.assertEqual(bytes(MP4(path).tags[MP4_SOURCE_KEY][0]).decode(), self.full.source_url)

    def test_selective_cover_removal_preserves_source(self):
        for extension in FORMATS:
            with self.subTest(extension=extension):
                path = self.make_audio(extension)
                self.writer.write(path, self.full)
                self.writer.update(path, {"cover": None})
                if extension == "mp3":
                    tags = ID3(path)
                    self.assertFalse(tags.getall("APIC"))
                    self.assertEqual(tags.getall("WOAS")[0].url, self.full.source_url)
                elif extension == "wav":
                    tags = WAVE(path).tags
                    self.assertFalse(tags.getall("APIC"))
                    self.assertEqual(tags.getall("WOAS")[0].url, self.full.source_url)
                elif extension == "m4a":
                    tags = MP4(path).tags
                    self.assertNotIn("covr", tags)
                    self.assertEqual(bytes(tags[MP4_SOURCE_KEY][0]).decode(), self.full.source_url)
                else:
                    audio = FLAC(path)
                    self.assertFalse(audio.pictures)
                    self.assertEqual(audio[VORBIS_SOURCE_KEY][0], self.full.source_url)

    def test_selective_cover_replacement_keeps_other_id3_pictures(self):
        path = self.make_audio("mp3")
        self.writer.write(path, self.full)
        tags = ID3(path)
        tags.add(APIC(encoding=3, mime="image/jpeg", type=4, desc="Cover_", data=b"back"))
        tags.save(path, v2_version=3)
        self.writer.update(path, {"cover": self.full.cover})
        pictures = ID3(path).getall("APIC")
        self.assertEqual({int(p.type): p.data for p in pictures}, {3: self.full.cover, 4: b"back"})

    def test_rewriting_does_not_duplicate_tags(self):
        for extension in ("mp3", "wav"):
            with self.subTest(extension):
                path = self.make_audio(extension)
                self.writer.write(path, self.full)
                self.writer.write(path, self.full)
                id3 = ID3(path) if extension == "mp3" else WAVE(path).tags
                for frame in ("TIT2", "TALB", "TDRC", "WOAS", "APIC"):
                    self.assertEqual(len(id3.getall(frame)), 1, frame)

    def test_id3_is_saved_as_version_2_3_with_the_year_in_tyer(self):
        # O Windows Explorer lê ID3v2.3 melhor. Lido sem conversão (translate=False),
        # o arquivo mostra o que está no disco: o ano em TYER, que é o frame da v2.3.
        path = self.make_audio("mp3")
        self.writer.write(path, self.full)
        raw = ID3(path, translate=False)
        self.assertEqual(raw.version[:2], (2, 3))
        self.assertEqual([str(f.text[0]) for f in raw.getall("TYER")], ["2024"])
        self.assertEqual(raw.getall("TDRC"), [])

    def test_unsupported_or_broken_files_give_a_readable_error(self):
        # FLAC tem cabeçalho obrigatório; um MP3 sem etiqueta apenas recebe uma nova.
        broken = self.dir / "quebrado.flac"
        broken.write_bytes(b"isto nao e audio")
        for path in (self.dir / "a.ogg", broken):
            with self.subTest(path.name), self.assertRaises(ExtractionError):
                self.writer.write(path, self.full)


if __name__ == "__main__":
    unittest.main()
