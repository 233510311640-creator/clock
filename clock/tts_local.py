"""Local text to speech with Kokoro (82M model, Apache 2.0) through kokoro-onnx. No account, no key, works offline.

Optional: used when CLOCK_TTS=kokoro. Needs `pip install -r requirements-kokoro.txt` and the model files
(`python -m clock.tts_local download`, about 350 MB, saved to models/kokoro/). If anything is missing or fails, the
caller falls back to edge-tts, so she always speaks.
"""
import sys
import threading
import urllib.request
import wave

from . import config as C

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")

_lock = threading.Lock()
_engine = None
_off_reason = ""


class LocalTtsError(Exception):
    pass


def reset():
    """For tests: forget the loaded model and any session-wide failure."""
    global _engine, _off_reason
    _engine, _off_reason = None, ""


def model_files():
    return [C.KOKORO_DIR / f for f in FILES]


def installed() -> bool:
    return all(p.is_file() for p in model_files())


def usable() -> bool:
    return C.TTS_ENGINE == "kokoro" and not _off_reason


def _disable(reason: str):
    global _off_reason
    if not _off_reason:
        _off_reason = reason
        print(f"(Kokoro off for this session: {reason}. Using edge-tts.)")


def _load():
    global _engine
    if _engine is None:
        if not installed():
            raise LocalTtsError("model files missing; run: python -m clock.tts_local download")
        try:
            from kokoro_onnx import Kokoro
        except ImportError:
            raise LocalTtsError("kokoro-onnx is not installed; run: pip install -r requirements-kokoro.txt") from None
        _engine = Kokoro(str(model_files()[0]), str(model_files()[1]))
    return _engine


def warm():
    """Load the model now so the first spoken line is not slow. Never raises."""
    try:
        with _lock:
            _load()
    except Exception as e:
        _disable(str(e) if isinstance(e, LocalTtsError) else f"{type(e).__name__}: {e}")


def synthesize(text: str, path: str):
    """Write a wav file for `text` to `path`. Raises LocalTtsError; setup problems also switch Kokoro off for the session."""
    import numpy as np
    try:
        with _lock:
            k = _load()
            lang = "en-gb" if C.KOKORO_VOICE.startswith("b") else "en-us"
            samples, rate = k.create(text, voice=C.KOKORO_VOICE, speed=C.KOKORO_SPEED, lang=lang)
    except LocalTtsError as e:
        _disable(str(e))
        raise
    except Exception as e:
        raise LocalTtsError(f"{type(e).__name__}: {e}") from None
    if len(samples) == 0:
        raise LocalTtsError("empty audio")
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm.tobytes())


def download():
    """Fetch the model files into models/kokoro/ (about 350 MB)."""
    C.KOKORO_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        dest = C.KOKORO_DIR / name
        if dest.is_file():
            print(f"{name}: already there")
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        print(f"downloading {name} ...")
        with urllib.request.urlopen(RELEASE + name, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done >> 20} / {total >> 20} MB", end="", flush=True)
        tmp.replace(dest)  # only a finished download gets the real name
        print()


if __name__ == "__main__":
    if sys.argv[1:] == ["download"]:
        download()
    else:
        print("usage: python -m clock.tts_local download")
