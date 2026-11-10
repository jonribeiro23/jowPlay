import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from tests.qt_support import dispose, qt_app
from ytdown.domain.library import Track
from ytdown.presentation.qt.properties_dialog import PropertiesDialog


class PropertiesDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_save_sends_fields_to_use_case(self):
        track = Track("song.mp3", "Old", datetime.now(), id=1)
        edit = Mock(return_value=track)
        dialog = PropertiesDialog(track, edit)
        try:
            dialog.fields["title"].setText("Novo")
            dialog.fields["artist"].setText("Artista")
            dialog.fields["genre"].setText("Rock")
            for name in ("title", "artist", "genre"):
                dialog.checks[name].setChecked(True)
            dialog.fields["year"].setValue(2024)
            dialog.save()
            self.assertEqual(edit.call_args.args[0], 1)
            self.assertEqual(edit.call_args.args[1]["title"], "Novo")
            self.assertEqual(edit.call_args.args[1]["artist"], "Artista")
            self.assertEqual(edit.call_args.args[1]["genre"], "Rock")
            self.assertEqual(edit.call_args.args[1]["year"], 2024)
            self.assertEqual(set(edit.call_args.args[1]), {"title", "artist", "genre", "year"})
        finally:
            dispose(dialog)

    def test_mixed_values_apply_only_selected_fields_and_cover_removal(self):
        first = Track("one.mp3", "Um", datetime.now(), artist="A", genre="Rock", id=1)
        second = Track("two.mp3", "Dois", datetime.now(), artist="B", genre="Rock", id=2)
        edit = Mock(side_effect=[first, second])
        dialog = PropertiesDialog([first, second], edit)
        try:
            self.assertEqual(dialog.fields["artist"].placeholderText(), "Valores mistos")
            dialog.fields["genre"].setText("Jazz")
            dialog.checks["genre"].setChecked(True)
            dialog.remove_cover()
            dialog.save()
            self.assertEqual(edit.call_count, 2)
            for call in edit.call_args_list:
                self.assertEqual(call.args[1], {"genre": "Jazz", "cover": None})
        finally:
            dispose(dialog)

    def test_batch_continues_after_failure(self):
        from ytdown.domain.errors import LibraryError
        first = Track("one.mp3", "Um", datetime.now(), id=1)
        second = Track("two.mp3", "Dois", datetime.now(), id=2)
        edit = Mock(side_effect=[LibraryError("bloqueado"), second])
        dialog = PropertiesDialog([first, second], edit)
        try:
            dialog.fields["genre"].setText("Jazz")
            dialog.checks["genre"].setChecked(True)
            with patch("ytdown.presentation.qt.properties_dialog.QMessageBox.warning") as warning:
                dialog.save()
            self.assertEqual(edit.call_count, 2)
            self.assertEqual(dialog.tracks, [second])
            self.assertIn("bloqueado", warning.call_args.args[2])
        finally:
            dispose(dialog)

    def test_choose_cover_loads_jpeg_for_update(self):
        from ytdown.infrastructure.resources import asset
        from ytdown.infrastructure.covers import PillowCoverLoader
        track = Track("one.mp3", "Um", datetime.now(), id=1)
        edit = Mock(return_value=track)
        dialog = PropertiesDialog(track, edit, cover_loader=PillowCoverLoader(asset("default_cover.jpg")))
        try:
            with patch("ytdown.presentation.qt.properties_dialog.QFileDialog.getOpenFileName",
                       return_value=(str(asset("default_cover.jpg")), "")):
                dialog.choose_cover()
            dialog.save()
            self.assertTrue(edit.call_args.args[1]["cover"].startswith(b"\xff\xd8"))
            self.assertEqual(set(edit.call_args.args[1]), {"cover"})
        finally:
            dispose(dialog)

    def test_menu_and_shortcuts_are_available_for_single_selection(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from tests.fakes import FakeAudioPlayer, FakeLibraryStorage, InMemoryTrackRepository
        from ytdown.application.playback import Playback
        from ytdown.infrastructure.json_settings import JsonSettings
        from ytdown.presentation.qt.songs_page import SongsPage
        repo = InMemoryTrackRepository()
        repo.add(Track("song.mp3", "Song", datetime.now()))
        storage = FakeLibraryStorage()
        with TemporaryDirectory() as temp:
            page = SongsPage(repo, Playback(FakeAudioPlayer(), storage), JsonSettings(Path(temp) / "settings"), storage=storage)
            try:
                page.track_actions.edit_properties = Mock()
                page.table.selectRow(0)
                self.assertIn("Propriedades", [action.text() for action in page.track_actions.make_menu().actions()])
                self.assertEqual(page.track_actions.properties_shortcut.key().toString(), "Alt+Return")
                self.assertEqual(page.track_actions.properties_enter_shortcut.key().toString(), "Alt+Enter")
            finally:
                dispose(page)
