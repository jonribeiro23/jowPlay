import unittest
import ctypes
from unittest.mock import Mock
from unittest.mock import patch

from ytdown.application.ports import PlayerState
from ytdown.presentation.qt.taskbar_controls import TaskbarPlayback
from ytdown.infrastructure.windows_taskbar import MSG, WindowsThumbnailControls


class TaskbarPlaybackTests(unittest.TestCase):
    def test_confirmed_state_and_shutdown(self):
        playback = Mock(state=PlayerState.STOPPED)
        controls = Mock()
        binding = TaskbarPlayback(playback, controls)
        controls.set_playing.assert_called_once_with(False)
        binding.on_state_changed(PlayerState.PLAYING)
        controls.set_playing.assert_called_with(True)
        binding.on_state_changed(PlayerState.PAUSED)
        controls.set_playing.assert_called_with(False)
        binding.shutdown()
        binding.shutdown()
        playback.remove_listener.assert_called_once_with(binding)
        controls.shutdown.assert_called_once()

    def test_native_messages_reinitialize_dispatch_and_survive_failure(self):
        with patch("ytdown.infrastructure.windows_taskbar.sys.platform", "other"):
            controls = WindowsThumbnailControls(Mock(), Mock(), Mock(), Mock())
        controls.hwnd = 123
        controls.message = 0xc001
        controls._connect = Mock()
        controls._send = Mock()
        msg = MSG(hwnd=123, message=controls.message)
        self.assertEqual(controls.nativeEventFilter(None, ctypes.addressof(msg)), (False, 0))
        self.assertTrue(controls.ready)
        controls.nativeEventFilter(None, ctypes.addressof(msg))
        self.assertEqual(controls._connect.call_count, 2)
        controls.set_playing(True)
        controls._send.assert_called_with(16)
        msg.message = 0x111
        msg.wParam = (0x1800 << 16) | 2
        self.assertEqual(controls.nativeEventFilter(None, ctypes.addressof(msg)), (True, 0))
        controls.actions[2].assert_called_once()
        msg.hwnd = 456
        self.assertEqual(controls.nativeEventFilter(None, ctypes.addressof(msg)), (False, 0))
        controls._send.side_effect = OSError("falha")
        with self.assertLogs("ytdown.infrastructure.windows_taskbar", level="ERROR"):
            controls.set_playing(False)
        controls.shutdown()


if __name__ == "__main__":
    unittest.main()
