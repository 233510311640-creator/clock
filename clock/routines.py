"""Recurring routines: a spoken briefing at a set time on chosen days. Stored as JSON, survive restarts.

A routine speaks fixed parts (greeting text, time, weather, today's reminders). It never runs the model or
any other tool on its own, so nothing a web page says can change what it does.
"""
import datetime
import json
import threading
import time
import uuid

from . import config as C
from . import reminders

_lock = threading.Lock()
PARTS = ("time", "weather", "reminders")
MAX_ROUTINES = 10
CATCH_UP = datetime.timedelta(hours=2)  # a routine missed by less than this is spoken late; older ones are skipped
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _load() -> list:
    try:
        return json.loads(C.ROUTINES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(items: list):
    C.ROUTINES_FILE.write_text(json.dumps(items, indent=1), encoding="utf-8")


def parse_days(spec: str) -> list:
    """'daily' | 'weekdays' | 'weekends' | 'mon,wed,fri' -> sorted weekday numbers (Monday = 0). Raises ValueError."""
    spec = (spec or "daily").lower().replace(" ", "")
    if spec in ("daily", "everyday", "every day"):
        return list(range(7))
    if spec == "weekdays":
        return list(range(5))
    if spec == "weekends":
        return [5, 6]
    days = set()
    for word in spec.split(","):
        if word[:3] not in _DAYS:
            raise ValueError(f"unknown day '{word}'")
        days.add(_DAYS.index(word[:3]))
    return sorted(days)


def parse_time(spec: str) -> str:
    """'8:30' or '08:30' (24-hour) -> '08:30'. Raises ValueError."""
    h, _, m = spec.strip().partition(":")
    hour, minute = int(h), int(m or 0)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"bad time '{spec}'")
    return f"{hour:02d}:{minute:02d}"


def parse_parts(spec: str) -> list:
    parts = [p for p in (spec or "").lower().replace(" ", "").split(",") if p]
    bad = [p for p in parts if p not in PARTS]
    if bad:
        raise ValueError(f"unknown part '{bad[0]}'; choose from {', '.join(PARTS)}")
    return parts


def _days_label(days: list) -> str:
    if days == list(range(7)):
        return "every day"
    if days == list(range(5)):
        return "on weekdays"
    if days == [5, 6]:
        return "on weekends"
    return "on " + ", ".join(_DAYS[d].capitalize() for d in days)


def _clock_label(hhmm: str) -> str:
    return datetime.datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")


def add(at: str, days: str = "daily", parts: str = "", text: str = "") -> str:
    when, day_list, part_list = parse_time(at), parse_days(days), parse_parts(parts)
    if not part_list and not text.strip():
        return "A routine needs something to say: give `text` or `include` (time, weather, reminders)."
    with _lock:
        items = _load()
        if len(items) >= MAX_ROUTINES:
            return f"Too many routines (limit {MAX_ROUTINES}). Cancel one first."
        item = {"id": uuid.uuid4().hex[:6], "time": when, "days": day_list, "parts": part_list,
                "text": text.strip(), "last_run": ""}
        _save(items + [item])
    return f"Routine set for {_clock_label(when)} {_days_label(day_list)}."


def listing() -> str:
    with _lock:
        items = sorted(_load(), key=lambda i: i["time"])
    if not items:
        return "No routines."
    return "\n".join(
        f"[{i['id']}] {_clock_label(i['time'])} {_days_label(i['days'])}: "
        + ", ".join(i["parts"] + ([f"\"{i['text']}\""] if i["text"] else []))
        for i in items)


def cancel(key: str) -> str:
    """Cancel by id, or by a word from its text or parts."""
    key = key.lower().strip()
    with _lock:
        items = _load()
        hit = [i for i in items if i["id"] == key] or [
            i for i in items if key and (key in i["text"].lower() or key in i["parts"] or key == i["time"])]
        if not hit:
            return "No matching routine."
        _save([i for i in items if i not in hit])
    return f"Cancelled {len(hit)} routine(s)."


def _today_reminders(now: datetime.datetime) -> str:
    end = now.replace(hour=23, minute=59, second=59)
    todays = sorted((i for i in reminders.pending() if now <= datetime.datetime.fromisoformat(i["due"]) <= end),
                    key=lambda i: i["due"])
    if not todays:
        return "No reminders today."
    bits = [f"{i['text']} at {datetime.datetime.fromisoformat(i['due']):%I:%M %p}".replace(" 0", " ") for i in todays]
    return "Today: " + "; ".join(bits) + "."


def compose(item: dict, now: datetime.datetime = None, late: bool = False) -> str:
    """The sentence(s) a routine speaks. Any part that fails (offline weather) is left out."""
    from . import web
    now = now or datetime.datetime.now()
    out = []
    if late:
        out.append("I missed this while I was off.")
    if item["text"]:
        out.append(item["text"])
    for part in item["parts"]:
        try:
            if part == "time":
                out.append(f"It is {now:%I:%M %p} on {now:%A}.".replace("It is 0", "It is "))
            elif part == "weather":
                out.append(web.weather())
            elif part == "reminders":
                out.append(_today_reminders(now))
        except Exception as e:
            print(f"(routine part '{part}' failed: {e})")
    return " ".join(out)


def _due(items: list, now: datetime.datetime) -> list:
    """Routines to run now, as (item, late). Marks each as run for today, including skipped stale ones."""
    today = now.date().isoformat()
    out = []
    for i in items:
        if now.weekday() not in i["days"] or i["last_run"] == today:
            continue
        at = datetime.datetime.combine(now.date(), datetime.time.fromisoformat(i["time"]))
        if now < at:
            continue
        i["last_run"] = today
        age = now - at
        if age <= CATCH_UP:
            out.append((i, age > datetime.timedelta(minutes=2)))
    return out


def pop_due(now: datetime.datetime = None) -> list:
    now = now or datetime.datetime.now()
    with _lock:
        items = _load()
        due = _due(items, now)
        if any(i["last_run"] == now.date().isoformat() for i in items):
            _save(items)
    return due


def start(speak):
    """Check every 15 s from a daemon thread. A routine runs at most once a day."""
    def loop():
        while True:
            try:
                for item, late in pop_due():
                    speak(compose(item, late=late))
            except Exception as e:
                print(f"(routine error: {e})")
            time.sleep(15)
    threading.Thread(target=loop, daemon=True).start()
