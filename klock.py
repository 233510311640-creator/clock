"""Control the Clock assistant: start it in the background, stop it, check on it.

    python klock.py start | stop | status | log
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PID_FILE = HERE / "klock.pid"
LOG_FILE = HERE / "klock.log"


def _running_pid():
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
    except ValueError:
        return None
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return pid if f'"{pid}"' in out else None


def start():
    pid = _running_pid()
    if pid:
        print(f"Clock is already running (PID {pid}).")
        return
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw if pythonw.exists() else sys.executable)
    log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    proc = subprocess.Popen([exe, "-m", "edith"], cwd=HERE, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=log, creationflags=flags,
                            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
    PID_FILE.write_text(str(proc.pid))
    print(f"Clock starting in the background (PID {proc.pid}). She'll say 'Clock online' when ready.")


def stop():
    pid = _running_pid()
    if not pid:
        print("Clock is not running.")
        PID_FILE.unlink(missing_ok=True)
        return
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    PID_FILE.unlink(missing_ok=True)
    print("Clock stopped.")


def status():
    pid = _running_pid()
    print(f"Clock is running (PID {pid})." if pid else "Clock is not running.")


def log():
    if not LOG_FILE.exists():
        print("No log yet.")
        return
    print("".join(LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[-30:]))


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
    {"start": start, "stop": stop, "status": status, "log": log, "mic": mic}.get(cmd, status)()
