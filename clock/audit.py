"""Append-only log of every tool call: what ran, with what, and how it ended. One JSON object per line."""
import datetime
import json
import threading

from . import config as C

MAX_BYTES = 1_000_000  # past this the file is rotated to .1, so the log cannot grow without bound
_lock = threading.Lock()

# How much a call can change. Logged with each entry; "destructive" calls also ask the user first.
RISK = {
    "close_app": "destructive", "forget": "destructive", "cancel_reminder": "destructive",
    "cancel_routine": "destructive", "add_routine": "write",
    "open_app": "write", "open_url": "write", "open_search_in_browser": "write", "set_timer": "write",
    "add_note": "write", "remember": "write", "set_reminder": "write", "volume": "write", "media": "write",
    "windows": "write", "clipboard": "write",
}


def risk(name: str, args: dict = None) -> str:
    if name == "clipboard" and (args or {}).get("action") != "write":
        return "read"
    return RISK.get(name, "read")


def _clip(value, limit=200):
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "..."
    return value


def record(name: str, args: dict, outcome: str, result="", tainted: bool = False):
    """outcome: ok | error | declined | blocked. Never raises: a full disk must not stop Clock."""
    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "tool": name, "risk": risk(name, args), "outcome": outcome, "after_untrusted": tainted,
        "args": {k: _clip(v) for k, v in (args or {}).items()},
        "result": _clip(str(result), 120),
    }
    try:
        with _lock:
            path = C.AUDIT_FILE
            if path.exists() and path.stat().st_size > MAX_BYTES:
                path.replace(path.with_suffix(path.suffix + ".1"))
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def tail(n: int = 10) -> list:
    try:
        lines = C.AUDIT_FILE.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def outcome_of(result) -> str:
    text = str(result)
    if text == "User declined.":
        return "declined"
    if text.startswith(("Tool error", "Unknown tool", "Capture failed")):
        return "error"
    return "ok"
