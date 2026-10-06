"""Control the Clock assistant: start it in the background, stop it, check on it.

    python klock.py start | stop | status | log | mic | wake-test | panel | tray | install | uninstall

`panel` opens the control window (tray menu > Open panel). `tray` shows a tray icon: red = off, green = on, amber = muted.
Left click starts Clock, or mutes / unmutes her while she runs. `install` puts that tray icon in your
Startup folder so it appears at every login (Clock waits until you start her there); `uninstall` removes it.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PID_FILE = HERE / "klock.pid"
TRAY_PID_FILE = HERE / "klock_tray.pid"
PANEL_PID_FILE = HERE / "klock_panel.pid"
LOG_FILE = HERE / "klock.log"


NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: without it each child process flashes a console from pythonw


def _pid_is_python(pid: int) -> bool:
    """True if `pid` is a live Python process. Uses the Windows API directly so nothing is spawned
    (the tray launcher polls this every couple of seconds, and a `tasklist` per poll flashes a window)."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
            return False
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return False
        # after a reboot Windows can hand the old PID to another program, so check it is really Python
        return "python" in buf.value.lower()
    finally:
        k32.CloseHandle(h)


def _running_pid(pid_file=PID_FILE):
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        return None
    return pid if _pid_is_python(pid) else None


def start(headless=False):
    """headless=True: the tray launcher owns the tray icon, so Clock doesn't make her own."""
    pid = _running_pid()
    if pid:
        print(f"Clock is already running (PID {pid}).")
        return
    (HERE / "klock.status").unlink(missing_ok=True)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw if pythonw.exists() else sys.executable)
    log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    proc = subprocess.Popen([exe, "-m", "clock"], cwd=HERE, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=log, creationflags=flags,
                            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8",
                                 **({"CLOCK_NO_TRAY": "1"} if headless else {})})
    PID_FILE.write_text(str(proc.pid))
    print(f"Clock starting in the background (PID {proc.pid}). She'll say 'Clock online' when ready.")


def stop():
    pid = _running_pid()
    if not pid:
        print("Clock is not running.")
        PID_FILE.unlink(missing_ok=True)
        return
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
    PID_FILE.unlink(missing_ok=True)
    print("Clock stopped.")


def status():
    pid = _running_pid()
    print(f"Clock is running (PID {pid})." if pid else "Clock is not running.")
    print("Starts at login: " + ("yes" if STARTUP_LINK.exists() else "no (python klock.py install)"))


def panel():
    """Open the control window (blocks). A second copy exits so you never get two windows."""
    if _running_pid(PANEL_PID_FILE) not in (None, os.getpid()):
        print("The Clock panel is already open.")
        return
    PANEL_PID_FILE.write_text(str(os.getpid()))
    from clock.panel import run
    try:
        run(lambda: _running_pid() is not None, lambda: start(headless=True), stop)
    finally:
        PANEL_PID_FILE.unlink(missing_ok=True)


def open_panel():
    """Launch the panel as its own windowless process (used by the tray icon)."""
    if _running_pid(PANEL_PID_FILE):
        return
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pythonw if pythonw.exists() else sys.executable), str(HERE / "klock.py"), "panel"],
                     cwd=HERE, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=0x00000008 | NO_WINDOW)


def tray():
    """Run the tray launcher (blocks). A second copy exits so you never get two icons."""
    if _running_pid(TRAY_PID_FILE) not in (None, os.getpid()):
        print("The Clock tray icon is already running.")
        return
    TRAY_PID_FILE.write_text(str(os.getpid()))
    from clock.launcher import run
    try:
        run(lambda: _running_pid() is not None, lambda: start(headless=True), stop, open_panel)
    finally:
        TRAY_PID_FILE.unlink(missing_ok=True)


def wake_test():
    """Show live wake-word scores so you can tune CLOCK_WAKE_THRESHOLD. Say the phrase, then talk normally."""
    import numpy as np
    from clock import config as C, wake
    from clock.audio import Mic
    models = wake.resolve_models()
    if not models:
        print("No wake model. Set CLOCK_WAKE_MODEL (e.g. hey_jarvis) or put models/hey_clock.onnx in place."
              "\nTraining steps: docs/wake_word_training.md")
        return
    gate = wake.WakeGate(models, C.WAKE_THRESHOLD, C.WAKE_VAD)
    mic = Mic()
    mic.open()
    print(f"Listening for {wake.describe()}  (threshold {C.WAKE_THRESHOLD}). Ctrl+C to stop."
          "\nSay the phrase a few times, then talk normally: the phrase should score above the threshold, "
          "normal speech should stay well below it.\n(Stop Clock first if she is running: `python klock.py stop`.)")
    try:
        while True:
            score = gate.score((np.clip(mic.get(), -1, 1) * 32767).astype(np.int16))
            if score >= 0.05:
                print(f"{score:4.2f} {'#' * int(score * 40):<40} {'<-- WAKE' if score >= C.WAKE_THRESHOLD else ''}")
    except KeyboardInterrupt:
        pass
    finally:
        mic.close()


def log():
    if not LOG_FILE.exists():
        print("No log yet.")
        return
    print("".join(LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[-30:]))


STARTUP_LINK = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/Clock.lnk"


def install():
    """Put a shortcut in the Startup folder that runs the tray icon (`klock.py tray`) with no console window."""
    py = Path(sys.executable)
    pythonw = py.with_name("pythonw.exe")
    target = str(pythonw if pythonw.exists() else py)
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
          "$s.TargetPath='%s';$s.Arguments='\"%s\" tray';$s.WorkingDirectory='%s';"
          "$s.WindowStyle=7;$s.Description='Clock tray icon (start or pause Clock)';$s.Save()"
          % (STARTUP_LINK, target, HERE / "klock.py", HERE))
    STARTUP_LINK.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    if STARTUP_LINK.exists():
        print(f"The Clock tray icon will now appear when you log in ({STARTUP_LINK.name} in your Startup folder).\n"
              "Click it (or right-click > Start Clock) when you want her listening.")
    else:
        print("Couldn't create the startup shortcut:", r.stderr.strip())


def uninstall():
    if STARTUP_LINK.exists():
        STARTUP_LINK.unlink()
        print("Clock will no longer start at login.")
    else:
        print("Clock wasn't set to start at login.")


def mic():
    import numpy as np
    import sounddevice as sd
    print(f"Using: {sd.query_devices(kind='input')['name']}")
    print("SPEAK NOW for 5 seconds (say anything)...")
    sr = 16000
    a = sd.rec(5 * sr, samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    x = a[:, 0]
    peak = max(float(np.sqrt(np.mean(x[i:i + 800] ** 2))) for i in range(0, len(x) - 800, 800))
    print(f"Peak level: {peak:.4f}  (Clock needs speech above about 0.015)")
    if peak < 0.001:
        print("-> Almost silent: the mic is muted, blocked, or the wrong device.")
    elif peak < 0.015:
        print("-> Heard something, but too quiet. Raise the mic volume in Windows Sound settings.")
    else:
        print("-> Mic level is good.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"start": start, "stop": stop, "status": status, "log": log, "mic": mic, "wake-test": wake_test,
     "panel": panel, "tray": tray, "install": install, "uninstall": uninstall}.get(cmd, status)()
