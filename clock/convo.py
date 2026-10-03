"""Conversation transcript shared with the control panel: one JSON line per thing said, newest last."""
import json
import time

from .tray import HERE

CONVO_FILE = HERE / "klock.convo.jsonl"
INBOX_FILE = HERE / "klock.inbox"  # lines typed in the panel, waiting for Clock to pick them up
KEEP = 200  # lines kept when the file is trimmed at startup


def reset():
    """Trim the file to the last KEEP lines so it can't grow forever."""
    try:
        lines = CONVO_FILE.read_text(encoding="utf-8").splitlines()[-KEEP:]
        CONVO_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except OSError:
        pass


def add(who: str, text: str):
    """who is 'you' or 'clock'. Never raises: the transcript is a nicety."""
    if not text.strip():
        return
    try:
        with open(CONVO_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%H:%M"), "who": who, "text": text.strip()}) + "\n")
    except OSError:
        pass


def read(limit=KEEP):
    try:
        lines = CONVO_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out


def send(text: str):
    """Panel side: queue a typed message for Clock."""
    with open(INBOX_FILE, "a", encoding="utf-8") as f:
        f.write(" ".join(text.split()) + chr(10))


def take():
    """Clock side: return and clear the queued typed messages."""
    taken = INBOX_FILE.with_suffix(".taken")
    try:
        INBOX_FILE.replace(taken)  # rename first so a message typed meanwhile isn't lost
        lines = taken.read_text(encoding="utf-8").splitlines()
        taken.unlink(missing_ok=True)
    except OSError:
        return []
    return [ln.strip() for ln in lines if ln.strip()]
