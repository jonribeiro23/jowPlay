"""RegisterExtractedTrack com dublês: pasta em memória, repositório em memória e leitor falso."""

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from tests.fakes import FakeLibraryStorage, FakeReader, InMemoryTrackRepository
from ytdown.application.library import RegisterExtractedTrack
from ytdown.domain.errors import ExtractionError, LibraryError
from ytdown.domain.library import DuplicatePolicy, Track
from ytdown.domain.models import AudioTags

NOW = datetime(2026, 11, 8, 10, 30)
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
TAGS = AudioTags(title="Me at the zoo", cover=b"capa", artist="jawed", album="Primeiros", genre="Vlog",
                 year=2005, track_no=1, source_url=URL)
EXPECTED_PATH = "jawed/Primeiros/01 - Me at the zoo.mp3"


class FailingRepository(InMemoryTrackRepository):
    def add(self, track):
        raise OSError("disco cheio")

    def update(self, track):
        raise OSError("disco cheio")


class RegisterTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.storage = FakeLibraryStorage()
        self.tracks = InMemoryTrackRepository()
        self.reader = FakeReader(duration_ms=19_000)
        self.register = RegisterExtractedTrack(self.storage, self.tracks, self.reader, clock=lambda: NOW)

    def downloaded(self, content=b"audio novo", name="Me at the zoo.mp3") -> Path:
        """O arquivo pronto na pasta temporária da extração."""
        path = self.temp / name
        path.write_bytes(content)
        return path

    def existing_track(self, rel_path=EXPECTED_PATH, content=b"audio antigo", **fields) -> Track:
        self.storage.files[rel_path] = content
        track = Track(rel_path=rel_path, title="Me at the zoo", added_at=datetime(2025, 1, 1), artist="jawed",
                      album="Primeiros", source_url=URL, play_count=7, **fields)
        return self.tracks.add(track)


class RegisterTests(RegisterTestCase):
    def test_file_goes_to_artist_album_number_title(self):
        file = self.downloaded()
        track = self.register(file, TAGS)
        self.assertEqual(track.rel_path, EXPECTED_PATH)
        self.assertEqual(self.storage.files, {EXPECTED_PATH: b"audio novo"})
        self.assertFalse(file.exists())  # Saiu da pasta temporária.

    def test_track_is_registered_with_the_tags_duration_and_source_url(self):
        track = self.register(self.downloaded(), TAGS)
        self.assertEqual(self.tracks.get(track.id), Track(
            rel_path=EXPECTED_PATH, title="Me at the zoo", added_at=NOW, artist="jawed", album="Primeiros",
            genre="Vlog", year=2005, track_no=1, duration_ms=19_000, source_url=URL, id=track.id,
        ))

    def test_empty_artist_and_album_use_the_unknown_folders(self):
        track = self.register(self.downloaded(), AudioTags(title="Solta", cover=b""))
        self.assertEqual(track.rel_path, "Artista desconhecido/Álbum desconhecido/Solta.mp3")

    def test_path_respects_the_room_left_by_the_library_folder(self):
        self.storage.max_length = 60
        track = self.register(self.downloaded(), replace(TAGS, title="Um título bem comprido " * 5))
        self.assertLessEqual(len(track.rel_path), 60)

    def test_unreadable_duration_does_not_block_the_track(self):
        self.reader.unreadable = True
        self.assertEqual(self.register(self.downloaded(), TAGS).duration_ms, 0)

    def test_name_taken_by_another_file_gets_a_number(self):
        self.storage.files[EXPECTED_PATH] = b"outro"
        track = self.register(self.downloaded(), replace(TAGS, source_url="https://www.youtube.com/watch?v=outro"))
        self.assertEqual(track.rel_path, "jawed/Primeiros/01 - Me at the zoo (1).mp3")
        self.assertEqual(self.storage.files[EXPECTED_PATH], b"outro")


class FailureTests(RegisterTestCase):
    def test_database_failure_removes_the_placed_file(self):
        register = RegisterExtractedTrack(self.storage, FailingRepository(), self.reader, clock=lambda: NOW)
        with self.assertRaisesRegex(LibraryError, "disco cheio"):
            register(self.downloaded(), TAGS)
        self.assertEqual(self.storage.files, {})
        self.assertEqual(self.storage.discarded, [EXPECTED_PATH])

    def test_database_failure_when_replacing_keeps_the_old_file(self):
        self.existing_track()
        failing = FailingRepository()
        failing._tracks, failing._next_id = self.tracks._tracks, self.tracks._next_id
        register = RegisterExtractedTrack(self.storage, failing, self.reader, clock=lambda: NOW)
        with self.assertRaises(LibraryError):
            register(self.downloaded(), TAGS, DuplicatePolicy.REPLACE)
        self.assertEqual(self.storage.files, {EXPECTED_PATH: b"audio antigo"})
        self.assertEqual(self.storage.trashed, [])

    def test_as_extraction_destination_errors_become_extraction_errors(self):
        register = RegisterExtractedTrack(self.storage, FailingRepository(), self.reader)
        with self.assertRaises(ExtractionError):
            register.destination().save(self.downloaded(), TAGS)


class DuplicateTests(RegisterTestCase):
    def test_duplicates_are_found_before_downloading_from_any_link_form(self):
        old = self.existing_track()
        urls = ["https://youtu.be/jNQXAC9IVRw", "https://www.youtube.com/watch?v=aaaaaaaaaaa",
                "https://music.youtube.com/watch?v=jNQXAC9IVRw&list=RD"]
        self.assertEqual(self.register.find_duplicates(urls), [(urls[0], old), (urls[2], old)])

    def test_no_duplicates_in_an_empty_library(self):
        self.assertEqual(self.register.find_duplicates(["https://youtu.be/jNQXAC9IVRw"]), [])

    def test_keep_both_adds_a_second_track_beside_the_first(self):
        old = self.existing_track()
        new = self.register(self.downloaded(), TAGS, DuplicatePolicy.KEEP_BOTH)
        self.assertNotEqual(new.id, old.id)
        self.assertEqual(new.rel_path, "jawed/Primeiros/01 - Me at the zoo (1).mp3")
        self.assertEqual(len(self.tracks.list_tracks()), 2)
        self.assertEqual(self.storage.trashed, [])

    def test_replace_reuses_the_track_and_sends_the_old_file_to_the_trash(self):
        old = self.existing_track()
        new = self.register(self.downloaded(), TAGS, DuplicatePolicy.REPLACE)
        self.assertEqual(new.id, old.id)
        self.assertEqual((new.play_count, new.added_at), (7, old.added_at))  # Estatísticas continuam.
        self.assertEqual((new.genre, new.year, new.duration_ms), ("Vlog", 2005, 19_000))  # Dados novos.
        self.assertEqual(self.storage.trashed, [EXPECTED_PATH])
        # O novo ganhou " (1)" porque o antigo ocupava o nome; depois, volta ao nome certo.
        self.assertEqual(new.rel_path, EXPECTED_PATH)
        self.assertEqual(self.storage.files, {EXPECTED_PATH: b"audio novo"})
        self.assertEqual(self.tracks.get(old.id).rel_path, EXPECTED_PATH)
        self.assertEqual(len(self.tracks.list_tracks()), 1)

    def test_replace_when_the_old_file_is_elsewhere(self):
        old = self.existing_track(rel_path="Outro/Lugar/zoo.mp3")
        new = self.register(self.downloaded(), TAGS, DuplicatePolicy.REPLACE)
        self.assertEqual((new.id, new.rel_path), (old.id, EXPECTED_PATH))
        self.assertEqual(self.storage.trashed, ["Outro/Lugar/zoo.mp3"])

    def test_replace_a_track_whose_file_was_missing(self):
        old = self.existing_track(missing=True)
        del self.storage.files[EXPECTED_PATH]
        new = self.register(self.downloaded(), TAGS, DuplicatePolicy.REPLACE)
        self.assertEqual((new.id, new.rel_path, new.missing), (old.id, EXPECTED_PATH, False))
        self.assertEqual(self.storage.trashed, [])

    def test_old_file_that_cannot_go_to_the_trash_stays_but_the_track_uses_the_new_one(self):
        old = self.existing_track()
        self.storage.fail_trash = True
        new = self.register(self.downloaded(), TAGS, DuplicatePolicy.REPLACE)
        self.assertEqual((new.id, new.rel_path), (old.id, "jawed/Primeiros/01 - Me at the zoo (1).mp3"))
        self.assertEqual(self.tracks.get(old.id).rel_path, new.rel_path)

    def test_replace_without_a_previous_track_just_adds(self):
        track = self.register(self.downloaded(), TAGS, DuplicatePolicy.REPLACE)
        self.assertEqual((track.rel_path, len(self.tracks.list_tracks())), (EXPECTED_PATH, 1))


class DestinationTests(RegisterTestCase):
    def test_destination_returns_the_absolute_path_of_the_new_file(self):
        path = self.register.destination().save(self.downloaded(), TAGS)
        self.assertEqual(path, self.storage.root / "jawed" / "Primeiros" / "01 - Me at the zoo.mp3")
        self.assertEqual(self.register.folder, self.storage.root)

    def test_destination_carries_the_chosen_policy(self):
        old = self.existing_track()
        self.register.destination(DuplicatePolicy.REPLACE).save(self.downloaded(), TAGS)
        self.assertEqual([t.id for t in self.tracks.list_tracks()], [old.id])


if __name__ == "__main__":
    unittest.main()
