"""Clock Control Center: a frameless window (pywebview) showing the UI in clock/ui/index.html.

Opens from the tray icon or the desktop shortcut. It is a separate process from Clock herself, so closing
the window never stops her. The page polls Api.get_state() and calls the other Api methods for actions.
"""
import os
import threading
import time
from pathlib import Path
from typing import Any

from . import config as C
from . import convo, reminders, settings, wake
from .tray import LOG, PID_FILE, STATUS_FILE

UI = Path(__file__).with_name("ui") / "index.html"


def state_of(running: bool, detail: str) -> str:
    """Map Clock's status text to the orb state the page knows."""
    if not running:
        return "off"
    if detail.startswith("mic"):
        return "alert"
    for key in ("hearing", "thinking", "speaking"):
        if detail.startswith(key):
            return key
    if detail.startswith(("listening", "waiting")):
        return "listening"
    return "loading"


class Api:
    """Exposed to the page as window.pywebview.api. Underscore names are private and stay hidden from it."""

    def __init__(self, is_running, start, stop):
        self._is_running, self._start, self._stop = is_running, start, stop
        self._busy = threading.Lock()
        self._window: Any = None  # the webview Window, set by run()

    def get_state(self):
        running = self._is_running()
        try:
            detail = STATUS_FILE.read_text(encoding="utf-8").strip() if running else ""
        except OSError:
            detail = ""
        try:
            up = int(time.time() - PID_FILE.stat().st_mtime) if running else None
        except OSError:
            up = None
        try:
            rems = sorted(reminders._load(), key=lambda i: i["due"])
        except Exception:
            rems = []
        msgs = convo.read()
        return {
            "running": running, "detail": detail, "state": state_of(running, detail), "uptime": up,
            "busy": self._busy.locked(), "msgs": msgs, "exchanges": sum(1 for m in msgs if m["who"] == "you"),
            "reminders": rems, "settings": settings.load(),
            "info": [["Model", C.MODEL], ["Wake word", wake.describe()], ["Speech", f"Whisper {C.WHISPER_MODEL}"], ["Voice", C.VOICE],
                     ["Weather city", C.CITY], ["Calls you", C.USER_NAME or "(no name)"]],
        }

    def send(self, text):
        if text and text.strip() and self._is_running():
            convo.send(text)

    def toggle(self):
        def work():
            if not self._busy.acquire(blocking=False):
                return
            try:
                self._stop() if self._is_running() else self._start()
            finally:
                self._busy.release()
        threading.Thread(target=work, daemon=True).start()

    def cancel(self, key):
        reminders.cancel(str(key))

    def set_setting(self, key, value):
        settings.save({str(key): bool(value)})

    def open_log(self):
        if LOG.exists():
            os.startfile(LOG)

    def open_memory(self):
        if C.MEMORY_FILE.exists():
            os.startfile(C.MEMORY_FILE)

    def minimize(self):
        self._window.minimize()

    def close(self):
        self._window.destroy()


def run(is_running, start, stop):
    import webview
    api = Api(is_running, start, stop)
    api._window = webview.create_window(
        "Clock", url=str(UI), js_api=api, width=1060, height=680, min_size=(960, 620),
        frameless=True, easy_drag=False, background_color="#07080f")
    webview.start()
