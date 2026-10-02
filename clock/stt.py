from faster_whisper import WhisperModel

from . import config as C
from .tools import APPS

_model = None

# Biases Whisper toward the words Clock actually expects, which helps with accents.
_PROMPT = ("Clock. Hi Clock. Hello Clock. Hey Clock. See you Clock. "
           f"Open {', '.join(APPS)}. Close an app. What time is it? Set a timer. "
           "Search the web. What is on my screen? Take a note. System status.")


def transcribe(audio) -> str:
    global _model
    if _model is None:
        _model = WhisperModel(C.WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=8)
    segments, _ = _model.transcribe(
        audio, language="en", beam_size=5, vad_filter=True,
        initial_prompt=_PROMPT, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segments).strip()
