"""Tray launcher: the one icon that lives in the tray from login. Start / pause Clock from its menu.

Clock itself isn't loaded until you start her, so logging in costs nothing. Pausing stops her process
completely, which also frees the microphone and the shared qwen model (handy while Cypher runs).
"""
import os
import threading
import time

from . import settings
from .tray import HERE, LOG, STATUS_FILE

# Clock's status text -> the tray icon that shows it (assets/tray_<name>.png, made by make_icons.py).
# Anything not listed counts as "active": she is hearing you, thinking or speaking.
_WAITING = ("listening", "loading")
_NO_MIC = ("mic silent", "mic unavailable")


def icon_state(running: bool, detail: str) -> str:
    if not running:
        return "off"
    if detail == "muted":
        return "muted"
    if detail.startswith(_NO_MIC):
        return "nomic"
    return "waiting" if detail in _WAITING or not detail else "active"


def run(is_running, start, stop, open_panel=None, autostart=False):
    """Show the tray icon. is_running() -> bool, start() / stop() control Clock's process.

    Left click: start Clock when she is off, otherwise mute / unmute her (she keeps running)."""
    import pystray
    from PIL import Image

    icons = {n: Image.open(HERE / "assets" / f"tray_{n}.png") for n in ("off", "waiting", "active", "muted", "nomic")}
    busy = threading.Lock()  # one start/stop at a time, off the tray thread so the menu never freezes

    def toggle(icon=None, item=None):
        def work():
            if not busy.acquire(blocking=False):
                return
            try:
                stop() if is_running() else start()
            finally:
                busy.release()
        threading.Thread(target=work, daemon=True).start()

    def click(icon=None, item=None):
        if not is_running():
            toggle()
        else:
            settings.save({"listening": not settings.load()["listening"]})

    def quit_all(icon, item):
        if is_running():
            stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: "Start Clock" if not is_running() else
                         ("Unmute (listen)" if not settings.load()["listening"] else "Mute (stop listening)"),
                         click, default=True),
        pystray.MenuItem("Open panel", lambda: open_panel(), visible=open_panel is not None),
        pystray.MenuItem(lambda item: "Stop Clock" if is_running() else "Start Clock", toggle),
        pystray.MenuItem("Open log", lambda: os.startfile(LOG) if LOG.exists() else None),
        pystray.MenuItem("Quit (stops Clock)", quit_all),
    )
    icon = pystray.Icon("clock-launcher", icons["off"], "Clock: off", menu)

    def watch():
        last = None
        while True:
            running = is_running()
            try:
                detail = STATUS_FILE.read_text(encoding="utf-8").strip() if running else ""
            except OSError:
                detail = ""
            state = (running, detail)
            if state != last:  # Windows redraws on every assignment, so only touch the icon on a change
                last = state
                icon.icon = icons[icon_state(running, detail)]
                icon.title = f"Clock: {detail or 'starting'}" if running else "Clock: off"
                icon.update_menu()
            time.sleep(0.7)

    def setup(icon):
        icon.visible = True
        threading.Thread(target=watch, daemon=True).start()
        if autostart and not is_running():
            toggle()

    icon.run(setup)
