"""System tray icon for Clock: shows status on hover, right-click menu to open the log or stop her."""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ICON = HERE / "assets" / "klock.png"
LOG = HERE / "klock.log"
PID_FILE = HERE / "klock.pid"


class Tray:
    def __init__(self):
        self.icon = None

    def start(self):
        try:
            import pystray
            from PIL import Image
            menu = pystray.Menu(
                pystray.MenuItem("Clock", None, enabled=False),
                pystray.MenuItem("Open log", lambda: os.startfile(LOG) if LOG.exists() else None),
                pystray.MenuItem("Stop Clock", self._quit),
            )
            self.icon = pystray.Icon("clock", Image.open(ICON), "Clock: starting", menu)
            self.icon.run_detached()
        except Exception as e:  # the tray is a nicety; never stop Clock over it
            print(f"(tray unavailable: {e})")
            self.icon = None

    def status(self, text: str):
        if self.icon:
            self.icon.title = f"Clock: {text}"

    def stop(self):
        if self.icon:
            self.icon.stop()

    def _quit(self, icon=None, item=None):
        PID_FILE.unlink(missing_ok=True)
        if self.icon:
            self.icon.stop()
        os._exit(0)
