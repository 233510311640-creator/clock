"""Keyboard and mouse control (Windows): type text, press keys, click, scroll in whatever window is in front.

She asks before acting, naming the window that will receive it; one yes covers further input for APPROVAL_SECONDS.
Risky key combinations (close window, Run box, task manager...) ask every time. Passwords are never typed on purpose:
the model is told so, and the secure sign-in / admin prompts ignore injected input anyway.
"""
import ctypes
import re
import time
from ctypes import wintypes

APPROVAL_SECONDS = 60
MAX_TYPE_CHARS = 2000
ALWAYS_ASK = {"alt+f4", "win+r", "ctrl+shift+esc", "ctrl+alt+delete", "win+x", "win+l", "alt+f4+ctrl"}

_u = ctypes.windll.user32
_approved_until = 0.0

VK = {"ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "windows": 0x5B,
      "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20, "backspace": 0x08,
      "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
      "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "insert": 0x2D, "printscreen": 0x2C,
      **{f"f{i}": 0x6F + i for i in range(1, 13)}}
_EXTENDED = {0x25, 0x26, 0x27, 0x28, 0x21, 0x22, 0x23, 0x24, 0x2D, 0x2E, 0x5B}


def parse_keys(combo: str):
    """"ctrl+shift+t" -> [0x11, 0x10, 0x54]. None if any part is not a key she knows."""
    out = []
    for part in re.split(r"\s*\+\s*", combo.strip().lower()):
        if part in VK:
            out.append(VK[part])
        elif len(part) == 1 and (part.isalnum()):
            out.append(ord(part.upper()))
        else:
            return None
    return out or None


def _norm(combo: str) -> str:
    return "+".join(re.split(r"\s*\+\s*", combo.strip().lower()))


# --- the only functions that touch the machine; tests replace them -------------------------------------------------
def _foreground_title() -> str:
    hwnd = _u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    _u.GetWindowTextW(hwnd, buf, 256)
    return buf.value or "the desktop"


class _KeyInput(ctypes.Structure):
    _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("extra", ctypes.c_size_t)]


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("data", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


class _Union(ctypes.Union):
    _fields_ = [("ki", _KeyInput), ("mi", _MouseInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _Union)]


def _send_unicode(text: str):
    """Type each character as a Unicode key press, so any language and symbol works."""
    events = []
    for ch in text:
        if ch == "\n":
            events += [_Input(1, _Union(ki=_KeyInput(0x0D, 0, 0, 0, 0))), _Input(1, _Union(ki=_KeyInput(0x0D, 0, 2, 0, 0)))]
            continue
        code = ord(ch)
        units = [code] if code < 0x10000 else [0xD800 + ((code - 0x10000) >> 10), 0xDC00 + ((code - 0x10000) & 0x3FF)]
        for unit in units:  # characters beyond the basic plane go in as a surrogate pair
            events.append(_Input(1, _Union(ki=_KeyInput(0, unit, 0x4, 0, 0))))
            events.append(_Input(1, _Union(ki=_KeyInput(0, unit, 0x4 | 0x2, 0, 0))))
    for i in range(0, len(events), 50):  # small batches keep the target window's queue happy
        batch = events[i:i + 50]
        arr = (_Input * len(batch))(*batch)
        _u.SendInput(len(batch), arr, ctypes.sizeof(_Input))
        time.sleep(0.01)


def _press(vks):
    for vk in vks:
        _u.keybd_event(vk, 0, 0x1 if vk in _EXTENDED else 0, 0)
    for vk in reversed(vks):
        _u.keybd_event(vk, 0, (0x1 if vk in _EXTENDED else 0) | 0x2, 0)


def _screen_box():
    """(left, top, right, bottom) of the whole desktop in physical pixels."""
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # coordinates from a screenshot are physical pixels
    except Exception:
        pass
    l, t = _u.GetSystemMetrics(76), _u.GetSystemMetrics(77)
    return l, t, l + _u.GetSystemMetrics(78), t + _u.GetSystemMetrics(79)


def _mouse(x, y, button: str, clicks: int):
    _u.SetCursorPos(int(x), int(y))
    down, up = {"left": (0x2, 0x4), "right": (0x8, 0x10), "middle": (0x20, 0x40)}[button]
    for _ in range(clicks):
        _u.mouse_event(down, 0, 0, 0, 0)
        _u.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.05)


def _wheel(notches: int):
    _u.mouse_event(0x0800, 0, 0, notches * 120, 0)


# --- the tools -----------------------------------------------------------------------------------------------------
def _ask(confirm, what: str, always: bool = False) -> bool:
    global _approved_until
    if not always and time.time() < _approved_until:
        return True
    if confirm(f"{what} in {_foreground_title()}?"):
        _approved_until = time.time() + APPROVAL_SECONDS
        return True
    return False


def forget_approval():
    global _approved_until
    _approved_until = 0.0


def type_text(text: str, confirm) -> str:
    if not text:
        return "Nothing to type."
    if len(text) > MAX_TYPE_CHARS:
        return f"That is too long to type ({len(text)} characters; the limit is {MAX_TYPE_CHARS})."
    if not _ask(confirm, f"Type {len(text)} characters"):
        return "User declined."
    _send_unicode(text)
    return f"Typed {len(text)} characters."


def press_keys(keys: str, confirm) -> str:
    vks = parse_keys(keys)
    if not vks:
        return f"I don't know the key combination '{keys}'. Use names like ctrl+c, alt+tab, enter, f5, win+d."
    if not _ask(confirm, f"Press {_norm(keys)}", always=_norm(keys) in ALWAYS_ASK):
        return "User declined."
    _press(vks)
    return f"Pressed {_norm(keys)}."


def click(x: int, y: int, confirm, button: str = "left", double: bool = False) -> str:
    left, top, right, bottom = _screen_box()
    if not (left <= x < right and top <= y < bottom):
        return f"That point is off the screen (it spans {left},{top} to {right - 1},{bottom - 1})."
    if not _ask(confirm, f"{'Double-click' if double else 'Click'} ({button}) at {x},{y}"):
        return "User declined."
    _mouse(x, y, button, 2 if double else 1)
    return f"Clicked at {x},{y}."


def scroll(direction: str, amount: int, confirm) -> str:
    amount = max(1, min(abs(amount or 3), 30))
    if not _ask(confirm, f"Scroll {direction} {amount}"):
        return "User declined."
    _wheel(amount if direction == "up" else -amount)
    return f"Scrolled {direction}."
