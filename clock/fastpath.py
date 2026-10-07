"""Instant answers for simple, unambiguous commands, so they skip the language model (about 1s instead of 3-8s).
Anything that is not an exact match falls through to the model, so this only ever handles the obvious cases."""
import datetime
import re

from . import audit
from .tools import APPS, resolve_app, run_tool

_LEAD = re.compile(r"^(?:(?:hey|ok|okay)\s+)?(?:clock\s+)?(?:(?:please|can you|could you|will you|would you)\s+)*", re.I)
_TAIL = re.compile(r"\s+(?:please|for me|now)$", re.I)
_NUM = r"(\d{1,3})"


def _clean(text: str) -> str:
    t = re.sub(r"[^\w\s%']", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    t = _LEAD.sub("", t)
    return _TAIL.sub("", t).strip()


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def _time(_m):
    n = _now()
    return f"It's {n.strftime('%I:%M %p').lstrip('0')}."


def _date(_m):
    n = _now()
    return f"It's {n.strftime('%A')}, {n.day} {n.strftime('%B %Y')}."


# (pattern, tool, args builder or None, reply builder given (match, tool result) or None to use the tool result)
_RULES = [
    (r"(?:what(?:'s| is)? the time|what time is it|what time is it now|tell me the time|the time)", None, None, lambda m, r: _time(m)),
    (r"(?:what(?:'s| is)? (?:the )?(?:date|day)(?: today)?|what day is it(?: today)?|what is today)", None, None, lambda m, r: _date(m)),
    (r"(?:volume|turn it|turn the volume|turn volume|make it) ?(?:up|louder)|louder|volume up", "volume", lambda m: {"action": "up"}, None),
    (r"(?:volume|turn it|turn the volume|turn volume|make it) ?(?:down|quieter)|quieter|volume down", "volume", lambda m: {"action": "down"}, None),
    (r"(?:set |put |make )?(?:the )?volume (?:to |at )?" + _NUM + r"(?: percent|%)?", "volume",
     lambda m: {"action": "set", "level": int(m.group(1))}, None),
    (r"(?:mute|mute (?:the )?(?:sound|volume|speakers?))", "volume", lambda m: {"action": "mute"}, None),
    (r"(?:unmute|unmute (?:the )?(?:sound|volume|speakers?))", "volume", lambda m: {"action": "unmute"}, None),
    (r"(?:pause|play|resume|pause (?:the )?(?:music|song|video)|play (?:the )?(?:music|song)|resume (?:the )?(?:music|song|video))",
     "media", lambda m: {"action": "play_pause"}, lambda m, r: "Done."),
    (r"(?:next|skip|next (?:song|track)|skip (?:this )?(?:song|track))", "media", lambda m: {"action": "next"}, lambda m, r: "Done."),
    (r"(?:previous|go back|previous (?:song|track)|last (?:song|track))", "media", lambda m: {"action": "previous"}, lambda m, r: "Done."),
    (r"(?:set )?(?:a )?timer (?:for )?" + _NUM + r" (second|minute|hour)s?", "set_timer",
     lambda m: {"seconds": int(m.group(1)) * {"second": 1, "minute": 60, "hour": 3600}[m.group(2)]},
     lambda m, r: f"Timer set for {m.group(1)} {m.group(2)}{'' if m.group(1) == '1' else 's'}."),
]
_RULES = [(re.compile(p + r"$", re.I), *rest) for p, *rest in _RULES]
_OPEN = re.compile(r"^(?:open|launch|start|run)\s+(?:up\s+)?(?:the\s+)?(?:app\s+)?([a-z0-9 ]{2,30})$", re.I)


def try_fast(text: str, speak, confirm, source: str = "local"):
    """Reply text if `text` is a simple command that was handled directly, else None."""
    t = _clean(text)
    if not t or len(t) > 60:
        return None
    for pat, tool, args, reply in _RULES:
        m = pat.match(t)
        if not m:
            continue
        if tool is None:
            return reply(m, "")
        a = args(m)
        result = run_tool(tool, a, speak, confirm)
        audit.record(tool, a, audit.outcome_of(result), result, False, source)
        return reply(m, result) if reply else result
    m = _OPEN.match(t)
    if m:
        name = m.group(1).strip()
        key = name if name in APPS else resolve_app(name)
        if key:  # unknown names go to the model, which may know what the user means
            result = run_tool("open_app", {"name": key}, speak, confirm)
            audit.record("open_app", {"name": key}, audit.outcome_of(result), result, False, source)
            return f"Opening {key}." if result.startswith("Opened") else result
    return None
