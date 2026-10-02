"""Long-term memory: short facts about the user that Clock keeps across sessions and sees on every turn."""
import datetime
import json
import threading
import uuid

from . import config as C

_lock = threading.Lock()
MAX_FACTS = 100        # stored
SHOWN_FACTS = 40       # most recent ones put in the prompt
SHOWN_CHARS = 2000


def _load() -> list:
    try:
        return json.loads(C.MEMORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(items: list):
    C.MEMORY_FILE.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")


def remember(fact: str) -> str:
    fact = " ".join(fact.split())[:300]
    if not fact:
        return "Nothing to remember."
    with _lock:
        items = _load()
        if any(i["text"].lower() == fact.lower() for i in items):
            return "I already know that."
        items.append({"id": uuid.uuid4().hex[:6], "text": fact, "saved": datetime.date.today().isoformat()})
        _save(items[-MAX_FACTS:])
    return "Remembered."


def forget(match: str) -> str:
    """Forget facts by id, or every fact containing the given words."""
    key = match.lower().strip()
    with _lock:
        items = _load()
        hit = [i for i in items if i["id"] == key] or [i for i in items if key and key in i["text"].lower()]
        if not hit:
            return "I don't have anything like that."
        _save([i for i in items if i not in hit])
    return "Forgot: " + "; ".join(i["text"] for i in hit)


def prompt_block() -> str:
    """The remembered facts, formatted for the system prompt (empty string if none)."""
    with _lock:
        items = _load()[-SHOWN_FACTS:]
    lines, total = [], 0
    for i in reversed(items):  # newest first, so the cap drops the oldest
        line = f"- {i['text']} (saved {i['saved']})"
        total += len(line)
        if total > SHOWN_CHARS:
            break
        lines.append(line)
    if not lines:
        return ""
    return "\nWhat you remember about the user (use it naturally, don't recite it):\n" + "\n".join(reversed(lines))
