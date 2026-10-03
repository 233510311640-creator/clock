"""Wake-word gate built on openWakeWord: a tiny model that listens all the time for one phrase.

With it, Whisper only runs after the phrase is heard, instead of transcribing every sound she picks up.
Pretrained phrases ship with openWakeWord (hey_jarvis, alexa, hey_mycroft, hey_rhasspy). For "Hey Clock" you
train your own model once; see docs/wake_word_training.md. Without a model she keeps using the Whisper match.
"""
import re
from functools import lru_cache
from pathlib import Path

from . import config as C

DEFAULT_MODEL = C.ROOT / "models" / "hey_clock.onnx"
PRETRAINED = ("alexa", "hey_mycroft", "hey_jarvis", "hey_rhasspy", "timer", "weather")


def resolve_models() -> list:
    """Model paths or pretrained names to load: CLOCK_WAKE_MODEL, else models/hey_clock.onnx if it exists."""
    names = [m.strip() for m in C.WAKE_MODEL.split(",") if m.strip()]
    if not names and DEFAULT_MODEL.exists():
        names = [str(DEFAULT_MODEL)]
    return names


def describe() -> str:
    """One line for the panel and the log. Doesn't load anything."""
    models = resolve_models()
    if C.WAKE_ENGINE == "whisper" or not models:
        return "Whisper phrase match"
    return "openWakeWord (" + ", ".join(Path(m).stem for m in models) + ")"


class WakeGate:
    def __init__(self, models: list, threshold: float, vad: float = 0.0):
        from openwakeword.model import Model
        self.threshold = threshold
        self.models = models
        try:
            self.model = Model(wakeword_models=models, inference_framework="onnx", vad_threshold=vad)
        except Exception:  # pretrained files download on first use
            from openwakeword import utils
            utils.download_models([m for m in models if m in PRETRAINED])
            self.model = Model(wakeword_models=models, inference_framework="onnx", vad_threshold=vad)

    def reset(self):
        self.model.reset()

    def score(self, frame) -> float:
        """frame: int16 mono at 16 kHz, ideally 1280 samples. Returns the best model's score, 0 to 1."""
        return max(self.model.predict(frame).values(), default=0.0)


def load_gate():
    """The gate to use, or None to fall back to the Whisper phrase match (reason is printed)."""
    if C.WAKE_ENGINE == "whisper":
        return None
    models = resolve_models()
    if not models:
        if C.WAKE_ENGINE == "oww":
            print("(wake: CLOCK_WAKE_ENGINE=oww but no model; set CLOCK_WAKE_MODEL or add models/hey_clock.onnx. "
                  "Using Whisper.)")
        return None
    missing = [m for m in models if m not in PRETRAINED and not Path(m).exists()]
    if missing:
        print(f"(wake: model file not found: {', '.join(missing)}. Using Whisper.)")
        return None
    try:
        return WakeGate(models, C.WAKE_THRESHOLD, C.WAKE_VAD)
    except Exception as e:  # missing package, bad model file: never leave her deaf
        print(f"(wake: openWakeWord unavailable ({e}). Using Whisper.)")
        return None


_GREETINGS = ("hey", "hi", "hello", "ok", "okay", "yo", "hay", "hiya")
# What Whisper tends to write for "Clock"; only used when the phrase contains "clock".
_CLOCK_VARIANTS = ("clock", "klock", "clark", "clack", "click", "cluck", "clok", "klok", "clog", "glock", "flock",
                   "cloak", "plock", "lock", "o'?clock")


def trigger_words(models: list) -> tuple:
    """Spoken words of the phrase the models listen for, from their file names (hey_jarvis_v0.1.onnx -> hey jarvis)."""
    words = []
    for m in models:
        for w in re.sub(r"_v\d.*$", "", Path(m).stem).lower().split("_"):
            if w and w not in words:
                words.append(w)
    return tuple(words) or ("clock",)


@lru_cache(maxsize=8)
def _lead_regex(words: tuple):
    names = [w for w in words if w not in _GREETINGS]
    alts = set(map(re.escape, names))
    if "clock" in names:
        alts |= set(_CLOCK_VARIANTS)
    greet = "|".join(_GREETINGS)
    name = "|".join(sorted(alts, key=len, reverse=True)) or "clock"
    return re.compile(rf"^\s*(?:(?:{greet})[, ]+)?(?:{name})\b[,.!? ]*", re.I), re.compile(rf"^\s*(?:{greet})\W*$", re.I)


def strip_trigger(text: str) -> str:
    """The command left after the wake phrase. The gate already decided she was addressed, so unlike
    strip_wake this never rejects: a mis-transcribed name is just left in if it can't be recognised."""
    lead, only_greeting = _lead_regex(trigger_words(resolve_models()))
    if only_greeting.match(text):
        return ""
    return lead.sub("", text, count=1).strip()
