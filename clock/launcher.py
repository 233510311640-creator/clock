"""Tray launcher: the one icon that lives in the tray from login. Start / pause Clock from its menu.

Clock itself isn't loaded until you start her, so logging in costs nothing. Pausing stops her process
completely, which also frees the microphone and the shared qwen model (handy while Cypher runs).
"""
import os
import threading
import time

from .tray import HERE, LOG, STATUS_FILE

ICON_ON, ICON_OFF = HERE / "assets" / "klock.png", HERE / "assets" / "klock_stop.png"


def run(is_running, start, stop, open_panel=None, autostart=False):
    """Show the tray icon. is_running() -> bool, start() / stop() control Clock's process."""
    import pystray
    from PIL import Image

    on, off = Image.open(ICON_ON), Image.open(ICON_OFF)
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

    def quit_all(icon, item):
        if is_running():
            stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open panel", lambda: open_panel(), default=True, visible=open_panel is not None),
        pystray.MenuItem(lambda item: "Pause Clock" if is_running() else "Start Clock", toggle,
                         default=open_panel is None),
        pystray.MenuItem("Open log", lambda: os.startfile(LOG) if LOG.exists() else None),
        pystray.MenuItem("Quit (stops Clock)", quit_all),
    )
    icon = pystray.Icon("clock-launcher", off, "Clock: paused", menu)

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
                icon.icon = on if running else off
                icon.title = f"Clock: {detail or 'starting'}" if running else "Clock: paused"
                icon.update_menu()
            time.sleep(1.5)

    def setup(icon):
        icon.visible = True
        threading.Thread(target=watch, daemon=True).start()
        if autostart and not is_running():
            toggle()

    icon.run(setup)
