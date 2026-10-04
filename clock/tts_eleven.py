"""ElevenLabs text to speech (Eleven v4). Optional: Clock uses it only when CLOCK_TTS=eleven and a key is set.

It needs internet and spends credits, so it is guarded:
  * a monthly character budget (CLOCK_ELEVEN_BUDGET, default 8000 of the 10,000 free credits); over it, edge-tts is used
  * a sentence longer than CLOCK_ELEVEN_MAX_CHARS goes to edge-tts instead
  * a rejected key, no credits left, or repeated failures turn ElevenLabs off until Clock restarts
Any failure raises ElevenError and the caller falls back to edge-tts, so she always speaks.
"""
import datetime
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import config as C

API = "https://api.elevenlabs.io"
OUTPUT_FORMAT = "mp3_44100_128"  # same container the edge-tts path plays
MAX_FAILS = 3  # consecutive network/server failures before giving up for this session

_lock = threading.Lock()
_off_reason = ""  # set when ElevenLabs is switched off for this session
_fails = 0


class ElevenError(Exception):
    pass


def reset():
    """For tests: forget the session state."""
    global _off_reason, _fails
    _off_reason, _fails = "", 0


def _month() -> str:
    return datetime.date.today().strftime("%Y-%m")


def used() -> int:
    """Characters sent this month."""
    try:
        data = json.loads(C.ELEVEN_USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return int(data.get("chars", 0)) if data.get("month") == _month() else 0


def _add_usage(chars: int):
    try:
        C.ELEVEN_USAGE_FILE.write_text(json.dumps({"month": _month(), "chars": used() + chars}), encoding="utf-8")
    except OSError:
        pass  # a counter that cannot be saved must not stop her speaking


def usable(text: str) -> bool:
    """True if this sentence should go to ElevenLabs."""
    if C.TTS_ENGINE != "eleven" or not C.ELEVEN_KEY or _off_reason:
        return False
    if len(text) > C.ELEVEN_MAX_CHARS:
        return False
    return used() + len(text) <= C.ELEVEN_BUDGET


def _disable(reason: str):
    global _off_reason
    if not _off_reason:
        _off_reason = reason
        print(f"(ElevenLabs off for this session: {reason}. Using edge-tts.)")


def _why(e: urllib.error.HTTPError) -> str:
    """ElevenLabs' own explanation for a 401/403 (for example a disabled free tier), clipped. Never contains the key."""
    try:
        detail = json.loads(e.read(2000).decode("utf-8", "replace")).get("detail", {})
        return str(detail.get("message", ""))[:160] if isinstance(detail, dict) else ""
    except Exception:
        return ""


def _invalid_key(e: urllib.error.HTTPError) -> bool:
    try:
        return "invalid_api_key" in e.read(2000).decode("utf-8", "replace")
    except Exception:
        return False


def synthesize(text: str, path: str):
    """Write mp3 speech for `text` to `path`. Raises ElevenError on any failure (the key is never in the message)."""
    global _fails
    url = (f"{API}/v1/text-to-speech/{urllib.parse.quote(C.ELEVEN_VOICE, safe='')}"
           f"?output_format={OUTPUT_FORMAT}")
    body = json.dumps({"text": text, "model_id": C.ELEVEN_MODEL}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "xi-api-key": C.ELEVEN_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        code = e.code
        if code in (401, 403):
            _disable(_why(e) or "the API key was rejected")
        elif code == 400 and _invalid_key(e):
            _disable("that is not a valid API key (use the secret key that starts with sk_, not the key ID)")
        elif code == 402:
            _disable("no credits left")
        elif code == 429:
            raise ElevenError("rate limited") from None  # only this sentence falls back
        else:
            _fails += 1
            if _fails >= MAX_FAILS:
                _disable(f"HTTP {code} {MAX_FAILS} times in a row")
        raise ElevenError(f"HTTP {code}") from None
    except Exception as e:
        _fails += 1
        if _fails >= MAX_FAILS:
            _disable(f"{type(e).__name__} {MAX_FAILS} times in a row")
        raise ElevenError(type(e).__name__) from None
    if len(audio) < 200:
        raise ElevenError("empty audio")
    with _lock:
        _fails = 0
        with open(path, "wb") as f:
            f.write(audio)
        _add_usage(len(text))


def balance() -> str:
    """For --check: remaining credits as text, or why it could not be read. Spends nothing."""
    req = urllib.request.Request(f"{API}/v1/user/subscription", headers={"xi-api-key": C.ELEVEN_KEY})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return "key rejected or missing the user_read permission"
        if e.code == 400 and _invalid_key(e):
            return "not a valid API key: use the secret key starting with sk_, not the key ID"
        return f"HTTP {e.code}"
    except Exception as e:
        return type(e).__name__
    left = d.get("character_limit", 0) - d.get("character_count", 0)
    return f"{left} credits left this period ({d.get('tier', '?')} plan)"


_TAG = None


def plain(text: str) -> str:
    """Remove [audio tags] like [whispers] or [laughs], for the screen, the phone and the edge-tts fallback."""
    global _TAG
    if _TAG is None:
        import re
        _TAG = (re.compile(r"\[[^\[\]]{1,40}\]"), re.compile(r"\s{2,}"))
    out = _TAG[0].sub("", text)
    return _TAG[1].sub(" ", out).strip()
