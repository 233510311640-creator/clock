import os
import tempfile
import wave

import numpy as np

from . import config as C
from .tools import APPS

_model = None
_phonon = None
_phonon_failed = False

# Biases Whisper toward the words Clock actually expects, which helps with accents.
_PROMPT = ("Clock. Hi Clock. Hello Clock. Hey Clock. See you Clock. "
           f"Open {', '.join(APPS)}. Close an app. What time is it? Set a timer. "
           "Search the web. What is on my screen? Take a note. System status.")


def _load_phonon():
    """Phonon-2 (fermion-research), run in-process on CPU. Uses fermion's internal loader, so pin the package version."""
    from fermion._speech import backends, fetch
    from fermion.transcribe import _resolve
    repo, key, pin, local_dir = _resolve("phonon-2")
    kind = backends.resolve("clock")
    model_dir = local_dir if local_dir is not None else fetch.ensure(repo, key, pin)
    return backends.load(kind, model_dir, profile=key, backend=pin["backend"], quiet=True)


def _transcribe_phonon(audio) -> str:
    global _phonon
    if _phonon is None:
        _phonon = _load_phonon()
    samples = np.asarray(audio, dtype="float32")
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="clock_stt_")
    os.close(fd)
    try:
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(C.SAMPLE_RATE)
            w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
        return _phonon.transcribe_detailed(path).triple()[0].strip()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def transcribe(audio) -> str:
    """Phonon-2 when CLOCK_STT allows it and it is installed, else faster-whisper. A Phonon error falls back for good."""
    global _phonon_failed
    if C.STT_ENGINE in ("auto", "phonon") and not _phonon_failed:
        try:
            return _transcribe_phonon(audio)
        except Exception as e:
            _phonon_failed = True
            print(f"(Phonon unavailable, using Whisper: {type(e).__name__}: {e})")
    return _transcribe_whisper(audio)


def _transcribe_whisper(audio) -> str:
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(C.WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=8)
    segments, _ = _model.transcribe(
        audio, language="en", beam_size=5, vad_filter=True,
        initial_prompt=_PROMPT, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segments).strip()
