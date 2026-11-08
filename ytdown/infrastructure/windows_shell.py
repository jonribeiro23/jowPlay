"""Integrações com o Windows que o Python não oferece: Lixeira e a pasta Música do usuário."""

from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes
from pathlib import Path

_FO_DELETE = 0x0003
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040  # Vai para a Lixeira em vez de apagar de vez.
_FOF_NOERRORUI = 0x0400

# FOLDERID_Music: respeita pastas redirecionadas (OneDrive, outro disco...).
_FOLDERID_MUSIC = uuid.UUID("{4BD8D571-6D19-48D3-BE97-422220080E43}")


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def send_to_recycle_bin(path: Path) -> None:
    """Envia o arquivo para a Lixeira, sem perguntar nada ao usuário. Falha com OSError."""
    operation = _SHFILEOPSTRUCTW(
        wFunc=_FO_DELETE,
        pFrom=str(path.resolve()) + "\0",  # A API exige uma lista terminada por dois nulos.
        fFlags=_FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT | _FOF_NOERRORUI,
    )
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(f"Não foi possível enviar {path.name} para a Lixeira (código {result}).")


class _GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_byte * 16)]


def music_folder() -> Path:
    """A pasta Música do usuário, onde quer que ela esteja."""
    guid = _GUID()
    ctypes.memmove(guid.data, _FOLDERID_MUSIC.bytes_le, 16)
    result_path = ctypes.c_wchar_p()
    try:
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(result_path)) == 0:
            return Path(result_path.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(result_path)
    return Path.home() / "Music"
