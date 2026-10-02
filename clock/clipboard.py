"""Windows clipboard text, via the Win32 API."""
import ctypes
import time
from ctypes import wintypes

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

_u, _k = ctypes.windll.user32, ctypes.windll.kernel32
_u.OpenClipboard.argtypes = [wintypes.HWND]
_u.GetClipboardData.argtypes = [wintypes.UINT]
_u.GetClipboardData.restype = wintypes.HANDLE
_u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_u.SetClipboardData.restype = wintypes.HANDLE
_k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_k.GlobalAlloc.restype = wintypes.HGLOBAL
_k.GlobalLock.argtypes = [wintypes.HGLOBAL]
_k.GlobalLock.restype = wintypes.LPVOID
_k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]


def _open():
    for _ in range(10):  # another program may hold the clipboard for a moment
        if _u.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise RuntimeError("the clipboard is busy")


def read() -> str:
    """Clipboard text, or '' if it holds something else (an image, files) or nothing."""
    _open()
    try:
        h = _u.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = _k.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            _k.GlobalUnlock(h)
    finally:
        _u.CloseClipboard()


def write(text: str):
    data = (text + "\0").encode("utf-16-le")
    h = _k.GlobalAlloc(GMEM_MOVEABLE, len(data))
    p = _k.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    _k.GlobalUnlock(h)
    _open()
    try:
        _u.EmptyClipboard()
        if not _u.SetClipboardData(CF_UNICODETEXT, h):
            raise RuntimeError("couldn't set the clipboard")
    finally:
        _u.CloseClipboard()
