"""Miniatura do Explorer. Todos os métodos são chamados na thread Qt da janela."""
import ctypes
import logging
import sys
import uuid
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

class GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]
    def __init__(self, value):
        super().__init__((ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))

class THUMBBUTTON(ctypes.Structure):
    _fields_ = [("mask", wintypes.DWORD), ("id", wintypes.UINT),
                ("bitmap", wintypes.UINT), ("icon", wintypes.HICON),
                ("tip", wintypes.WCHAR * 260), ("flags", wintypes.DWORD)]

class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT), ("private", wintypes.DWORD)]

class WindowsThumbnailControls(QAbstractNativeEventFilter):
    def __init__(self, window, previous, play_pause, next_track):
        super().__init__()
        self.window = window
        self.actions = {1: previous, 2: play_pause, 3: next_track}
        self.playing = False
        self.ready = False
        self.closed = False
        self.taskbar = ctypes.c_void_p()
        self.icons = []
        self.com_initialized = False
        self.app = QApplication.instance()
        if sys.platform != "win32" or self.app is None:
            return
        try:
            self.user32 = ctypes.WinDLL("user32", use_last_error=True)
            self.ole32 = ctypes.OleDLL("ole32")
            self.user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
            self.message = self.user32.RegisterWindowMessageW("TaskbarButtonCreated")
            if not self.message:
                raise OSError("RegisterWindowMessageW falhou")
            self.user32.CreateIcon.argtypes = [wintypes.HINSTANCE, ctypes.c_int, ctypes.c_int, ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_void_p, ctypes.c_void_p]
            self.user32.CreateIcon.restype = wintypes.HICON
            self.user32.DestroyIcon.argtypes = [wintypes.HICON]
            for name in ("previous", "play", "pause", "next"):
                self.icons.append(self._icon(name))
            self.hwnd = int(window.winId())
            self.app.installNativeEventFilter(self)
        except Exception:
            logger.exception("Controles da barra indisponíveis")
            self.shutdown()

    def _icon(self, name):
        # Ícones monocromáticos próprios; AND transparente, XOR branco.
        pixels = []
        for y in range(16):
            row = 0
            for x in range(16):
                triangle = 4 <= x <= 11 and abs(y - 7.5) <= (x - 3) * .65
                if name in ("play", "next"):
                    triangle = 4 <= x <= 11 and abs(y - 7.5) <= (12 - x) * .65
                on = ((4 <= x <= 6 or 9 <= x <= 11) and 3 <= y <= 12) if name == "pause" else triangle
                if name == "previous": on |= 3 <= x <= 4 and 3 <= y <= 12
                if name == "next": on |= 11 <= x <= 12 and 3 <= y <= 12
                row |= int(on) << (15 - x)
            pixels.extend((row >> 8, row & 255))
        xor = (ctypes.c_ubyte * 32)(*pixels)
        and_bits = (ctypes.c_ubyte * 32)(*(255 ^ b for b in pixels))
        icon = self.user32.CreateIcon(None, 16, 16, 1, 1, and_bits, xor)
        if not icon: raise OSError("CreateIcon falhou")
        return icon

    def _call(self, index, restype, argtypes, *args):
        table = ctypes.cast(self.taskbar, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        method = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(table[index])
        return method(self.taskbar, *args)

    def _connect(self):
        if self.taskbar:
            self._call(2, ctypes.c_ulong, [])
            self.taskbar = ctypes.c_void_p()
        if not self.com_initialized:
            # Qt pode já ter inicializado COM; S_OK e S_FALSE exigem CoUninitialize.
            hr = ctypes.windll.ole32.CoInitializeEx(None, 2)
            if hr in (0, 1): self.com_initialized = True
            elif hr != -2147417850: raise OSError(f"CoInitializeEx: {hr}")
        clsid = GUID("56FDF344-FD6D-11D0-958A-006097C9A090")
        iid = GUID("EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF")
        self.ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(self.taskbar))
        hr = self._call(3, ctypes.c_long, [])
        if hr < 0: raise OSError(f"HrInit: {hr}")

    def _buttons(self):
        values = [(1, self.icons[0], "Anterior"), (2, self.icons[2 if self.playing else 1], "Pausar" if self.playing else "Tocar"), (3, self.icons[3], "Próxima")]
        return (THUMBBUTTON * 3)(*(THUMBBUTTON(0x2 | 0x4 | 0x8, ident, 0, icon, tip, 0) for ident, icon, tip in values))

    def _send(self, index):
        buttons = self._buttons()
        hr = self._call(index, ctypes.c_long, [wintypes.HWND, wintypes.UINT, ctypes.POINTER(THUMBBUTTON)], self.hwnd, 3, buttons)
        if hr < 0: raise OSError(f"ThumbBar HRESULT {hr}")

    def nativeEventFilter(self, event_type, message):
        if self.closed: return False, 0
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(MSG)).contents
            if msg.hwnd != self.hwnd: return False, 0
            if msg.message == self.message:
                self.ready = False
                self._connect()
                self._send(15)  # ThumbBarAddButtons
                self.ready = True
            elif msg.message == 0x111 and (msg.wParam >> 16) & 0xffff == 0x1800:
                action = self.actions.get(msg.wParam & 0xffff)
                if action:
                    action()
                    return True, 0
        except Exception:
            logger.exception("Falha nos controles da barra")
        return False, 0

    def set_playing(self, playing):
        self.playing = playing
        if self.ready and not self.closed:
            try: self._send(16)  # ThumbBarUpdateButtons
            except Exception: logger.exception("Falha ao atualizar controles da barra")

    def shutdown(self):
        if self.closed: return
        self.closed = True
        self.ready = False
        try:
            if self.app: self.app.removeNativeEventFilter(self)
            if self.taskbar: self._call(2, ctypes.c_ulong, [])
        except Exception:
            logger.exception("Falha ao liberar controles da barra")
        finally:
            self.taskbar = ctypes.c_void_p()
            for icon in self.icons:
                try: self.user32.DestroyIcon(icon)
                except Exception: logger.exception("Falha ao liberar ícone")
            self.icons.clear()
            if self.com_initialized:
                ctypes.windll.ole32.CoUninitialize()
                self.com_initialized = False
