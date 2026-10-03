"""A small always-on-top HUD in the top-right corner: shows what Clock is doing and the last exchange.

It appears when she hears you, thinks or speaks, and hides the moment she goes back to listening
(listening states are shown in the tray only).
Runs tkinter in its own thread; every call is a no-op if tkinter or a display isn't available.
"""
import queue
import threading

from . import config as C

BG, FG, DIM, ACCENT = "#0b1320", "#d8f3ff", "#6f8ea3", "#35d0ff"
# Listening-type states stay in the tray only; the HUD only shows while she is hearing, thinking or speaking.
TRAY_ONLY = ("listening", "loading", "waiting for your request", "mic")
POLL_MS = 100
WIDTH = 360


class Hud:
    def __init__(self):
        self.q = queue.Queue()
        self.enabled = C.HUD

    def start(self):
        if not self.enabled:
            return
        threading.Thread(target=self._run, daemon=True, name="hud").start()

    # --- called from the main thread -------------------------------------------------------
    def status(self, text: str):
        self.q.put(("status", text))

    def heard(self, text: str):
        self.q.put(("heard", text))

    def reply(self, text: str):
        self.q.put(("reply", text))

    def stop(self):
        self.q.put(("quit", None))

    # --- tk thread -------------------------------------------------------------------------
    def _run(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception as e:  # no display / no tkinter: the HUD is a nicety
            print(f"(HUD unavailable: {e})")
            self.enabled = False
            return
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.9)
        root.configure(bg=BG, highlightbackground=ACCENT, highlightthickness=1)
        status = tk.Label(root, text="", bg=BG, fg=ACCENT, font=("Segoe UI Semibold", 10), anchor="w")
        heard = tk.Label(root, text="", bg=BG, fg=DIM, font=("Segoe UI", 10), anchor="w",
                         justify="left", wraplength=WIDTH - 24)
        reply = tk.Label(root, text="", bg=BG, fg=FG, font=("Segoe UI", 11), anchor="w",
                         justify="left", wraplength=WIDTH - 24)
        for w in (status, heard, reply):
            w.pack(fill="x", padx=12, pady=(8 if w is status else 2, 8 if w is reply else 0))
        root.withdraw()

        def place():
            root.update_idletasks()
            h = root.winfo_reqheight()
            root.geometry(f"{WIDTH}x{h}+{root.winfo_screenwidth() - WIDTH - 24}+48")

        def hide():
            root.withdraw()

        def show():
            place()
            root.deiconify()
            root.attributes("-topmost", True)

        tray_only = [True]

        def poll():
            try:
                while True:
                    kind, text = self.q.get_nowait()
                    if kind == "quit":
                        root.destroy()
                        return
                    if kind == "status":
                        status.config(text=("● " + text.upper()))
                        tray_only[0] = text.startswith(TRAY_ONLY)
                        if tray_only[0]:
                            hide()
                        else:
                            if text == "hearing you":  # a new exchange starts
                                heard.config(text="")
                                reply.config(text="")
                            show()
                    elif kind == "heard":
                        heard.config(text=f"you: {text}")
                        if not tray_only[0]:
                            show()
                    elif kind == "reply":
                        reply.config(text=text)
                        if not tray_only[0]:
                            show()
            except queue.Empty:
                pass
            root.after(POLL_MS, poll)

        poll()
        try:
            root.mainloop()
        except Exception as e:
            print(f"(HUD stopped: {e})")
            self.enabled = False
