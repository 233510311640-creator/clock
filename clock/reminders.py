"""Reminders and timers that survive restarts. Stored as JSON; a background thread announces them when due."""
import datetime
import json
import threading
import time
import uuid

from . import config as C

_lock = threading.Lock()


def _load() -> list:
    try:
        return json.loads(C.REMINDERS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(items: list):
    C.REMINDERS_FILE.write_text(json.dumps(items, indent=1), encoding="utf-8")


def add(due: datetime.datetime, text: str, kind: str = "reminder") -> dict:
    item = {"id": uuid.uuid4().hex[:6], "due": due.isoformat(timespec="seconds"), "text": text, "kind": kind}
    with _lock:
        _save(_load() + [item])
    return item


def parse_when(when: str) -> datetime.datetime:
    """Local time as 'YYYY-MM-DD HH:MM' (seconds optional)."""
    return datetime.datetime.fromisoformat(when.strip().replace("T", " "))


def describe(due: datetime.datetime) -> str:
    now = datetime.datetime.now()
    day = ("today" if due.date() == now.date() else
           "tomorrow" if due.date() == (now + datetime.timedelta(days=1)).date() else due.strftime("%A %d %B"))
    return f"{day} at {due:%I:%M %p}".replace(" 0", " ")


def listing() -> str:
    with _lock:
        items = sorted(_load(), key=lambda i: i["due"])
    if not items:
        return "No reminders or timers pending."
    return "\n".join(f"[{i['id']}] {describe(datetime.datetime.fromisoformat(i['due']))}: {i['text']}"
                     for i in items)


def pending() -> list:
    """All pending reminders and timers, as stored dicts (id, due ISO string, text, kind)."""
    with _lock:
        return _load()


def cancel(key: str) -> str:
    """Cancel by id, or by a word from the text."""
    key = key.lower().strip()
    with _lock:
        items = _load()
        hit = [i for i in items if i["id"] == key] or [i for i in items if key and key in i["text"].lower()]
        if not hit:
            return "No matching reminder."
        _save([i for i in items if i not in hit])
    return f"Cancelled {len(hit)}: " + "; ".join(i["text"] for i in hit)


def _pop_due() -> list:
    now = datetime.datetime.now()
    with _lock:
        items = _load()
        due = [i for i in items if datetime.datetime.fromisoformat(i["due"]) <= now]
        if due:
            _save([i for i in items if i not in due])
    return due


def _line(i: dict) -> str:
    due = datetime.datetime.fromisoformat(i["due"])
    late = datetime.datetime.now() - due > datetime.timedelta(minutes=2)
    base = f"{i['text']} is done." if i["kind"] == "timer" else f"Reminder: {i['text']}."
    return f"While I was off, this came due {describe(due)}. {base}" if late else base


def start(speak):
    """Announce due reminders from a daemon thread. Anything overdue at startup is announced once."""
    def loop():
        while True:
            try:
                for i in _pop_due():
                    speak(_line(i))
            except Exception as e:
                print(f"(reminder error: {e})")
            time.sleep(2)
    threading.Thread(target=loop, daemon=True).start()
