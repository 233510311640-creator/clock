"""Window control (Windows): list, focus, minimize, maximize, snap, close, lock."""
import ctypes
import os
import time
from ctypes import wintypes

import psutil

_u = ctypes.windll.user32
_dwm = ctypes.windll.dwmapi
_ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_u.EnumWindows.argtypes = [_ENUMPROC, wintypes.LPARAM]
for _fn in ("IsWindowVisible", "IsIconic", "GetWindowTextLengthW"):
    getattr(_u, _fn).argtypes = [wintypes.HWND]
_u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_u.SetForegroundWindow.argtypes = [wintypes.HWND]
_u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
WM_CLOSE = 0x0010
VK_MENU, VK_LWIN, VK_LEFT, VK_RIGHT, VK_M = 0x12, 0x5B, 0x25, 0x27, 0x4D


def _windows() -> list:
    """Visible, titled, real top-level windows, front to back: [(hwnd, title, process_name)]."""
    found = []

    def cb(hwnd, _):
        if not _u.IsWindowVisible(hwnd) or _u.GetWindowTextLengthW(hwnd) == 0:
            return True
        if _u.GetWindowLongW(hwnd, -20) & 0x80:          # tool window
            return True
        cloaked = wintypes.DWORD()
        _dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
        if cloaked.value:                                 # hidden UWP / other-desktop window
            return True
        buf = ctypes.create_unicode_buffer(256)
        _u.GetWindowTextW(hwnd, buf, 256)
        if buf.value == "Program Manager":
            return True
        pid = wintypes.DWORD()
        _u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            proc = psutil.Process(pid.value).name()
        except psutil.Error:
            proc = ""
        found.append((hwnd, buf.value, proc))
        return True

    _u.EnumWindows(_ENUMPROC(cb), 0)
    return found


def _find(target: str):
    t = (target or "").lower().strip()
    if not t:
        return None
    for w in _windows():
        if t in w[1].lower() or t in os.path.splitext(w[2])[0].lower():
            return w
    return None


def _keys(*vks):
    for vk in vks:
        _u.keybd_event(vk, 0, 0, 0)
    for vk in reversed(vks):
        _u.keybd_event(vk, 0, 2, 0)


def _focus(hwnd):
    if _u.IsIconic(hwnd):
        _u.ShowWindow(hwnd, SW_RESTORE)
    _u.keybd_event(VK_MENU, 0, 0, 0)   # a tap of Alt lets us take the foreground
    _u.SetForegroundWindow(hwnd)
    _u.keybd_event(VK_MENU, 0, 2, 0)
    time.sleep(0.15)


def control(action: str, target: str = "", confirm=None) -> str:
    if action == "list":
        ws = _windows()[:15]
        return "\n".join(f"{t} ({p})" for _, t, p in ws) or "No open windows."
    if action == "minimize_all":
        _keys(VK_LWIN, VK_M)
        return "Minimized everything."
    if action == "lock":
        _u.LockWorkStation()
        return "Locked."
    w = _find(target)
    if not w:
        return f"No open window matches '{target}'."
    hwnd, title, proc = w
    if action == "focus":
        _focus(hwnd)
        return f"Switched to {title}."
    if action == "minimize":
        _u.ShowWindow(hwnd, SW_MINIMIZE)
        return f"Minimized {title}."
    if action == "maximize":
        _u.ShowWindow(hwnd, SW_MAXIMIZE)
        return f"Maximized {title}."
    if action == "restore":
        _u.ShowWindow(hwnd, SW_RESTORE)
        return f"Restored {title}."
    if action in ("snap_left", "snap_right"):
        _focus(hwnd)
        _keys(VK_LWIN, VK_LEFT if action == "snap_left" else VK_RIGHT)
        return f"Snapped {title} to the {action[5:]}."
    if action == "close":
        if confirm and not confirm(f"Close {title}?"):
            return "User declined."
        _u.PostMessageW(hwnd, WM_CLOSE, 0, 0)  # polite close: unsaved-work prompts still appear
        return f"Asked {title} to close."
    return f"Unknown window action {action}."
