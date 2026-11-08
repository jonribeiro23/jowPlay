import unittest

from ytdown.domain.library import UNKNOWN_ALBUM, UNKNOWN_ARTIST
from ytdown.domain.library_paths import (
    MAX_FOLDER_NAME,
    MIN_FILE_STEM,
    MIN_FOLDER_NAME,
    UNTITLED,
    library_path,
    safe_name,
)


class LibraryPathTests(unittest.TestCase):
    def test_artist_album_number_and_title(self):
        self.assertEqual(library_path("Ana", "Sol", "Manhã", 1, "mp3"), "Ana/Sol/01 - Manhã.mp3")
        self.assertEqual(library_path("Ana", "Sol", "Manhã", 12, "mp3"), "Ana/Sol/12 - Manhã.mp3")
        self.assertEqual(library_path("Ana", "Sol", "Manhã", 103, "mp3"), "Ana/Sol/103 - Manhã.mp3")

    def test_number_only_when_it_exists(self):
        self.assertEqual(library_path("Ana", "Sol", "Manhã", None, "flac"), "Ana/Sol/Manhã.flac")
        self.assertEqual(library_path("Ana", "Sol", "Manhã", 0, "flac"), "Ana/Sol/Manhã.flac")

    def test_missing_fields_use_the_unknown_names(self):
        self.assertEqual(library_path("", "  ", "", None, "m4a"), f"{UNKNOWN_ARTIST}/{UNKNOWN_ALBUM}/{UNTITLED}.m4a")

    def test_extension_is_normalized(self):
        self.assertEqual(library_path("A", "B", "C", None, ".MP3"), "A/B/C.mp3")

    def test_accents_are_kept(self):
        self.assertEqual(library_path("João", "Ação", "Canção", 2, "wav"), "João/Ação/02 - Canção.wav")

    def test_whole_path_fits_the_limit(self):
        path = library_path("A" * 200, "B" * 200, "C" * 500, 7, "flac", max_length=150)
        self.assertLessEqual(len(path), 150)
        artist, album, _ = path.split("/")
        self.assertEqual((len(artist), len(album)), (MAX_FOLDER_NAME, MAX_FOLDER_NAME))

    def test_folders_shrink_when_the_title_alone_is_not_enough(self):
        path = library_path("A" * 200, "B" * 200, "C" * 500, None, "mp3", max_length=100)
        self.assertLessEqual(len(path), 100)
        artist, album, file_name = path.split("/")
        self.assertLess(len(artist), MAX_FOLDER_NAME)
        self.assertGreaterEqual(len(file_name), MIN_FILE_STEM)

    def test_nothing_is_cut_below_the_minimums(self):
        path = library_path("A" * 100, "B" * 100, "T" * 100, None, "mp3", max_length=10)
        artist, album, file_name = path.split("/")
        self.assertEqual((len(artist), len(album)), (MIN_FOLDER_NAME, MIN_FOLDER_NAME))
        self.assertEqual(len(file_name), MIN_FILE_STEM + len(".mp3"))


class SafeNameTests(unittest.TestCase):
    def name(self, text):
        return safe_name(text, "reserva", 50)

    def test_characters_forbidden_on_windows_are_replaced(self):
        self.assertEqual(self.name("AC/DC"), "AC_DC")
        self.assertEqual(self.name('Que? "Sim": <talvez> | a\\b *'), 'Que_ _Sim__ _talvez_ _ a_b _')
        self.assertEqual(self.name("linha\nnova\ttab"), "linha_nova_tab")

    def test_trailing_dots_and_spaces_are_removed(self):
        self.assertEqual(self.name("Vol. 2."), "Vol. 2")
        self.assertEqual(self.name("  Nome   com   espaços  "), "Nome com espaços")
        self.assertEqual(self.name("..."), "reserva")

    def test_reserved_device_names_are_avoided(self):
        for reserved in ("CON", "nul", "Com1", "LPT9", "aux.mix"):
            with self.subTest(reserved):
                self.assertEqual(self.name(reserved), reserved + "_")
        for normal in ("CONcerto", "Nulidade", "COM10"):
            with self.subTest(normal):
                self.assertEqual(self.name(normal), normal)

    def test_names_made_only_of_forbidden_characters_use_the_fallback(self):
        self.assertEqual(self.name("???"), "reserva")
        self.assertEqual(self.name(""), "reserva")

    def test_cut_names_do_not_end_in_space_or_dot(self):
        self.assertEqual(safe_name("abc. def", "x", 5), "abc")


if __name__ == "__main__":
    unittest.main()
