"""`python -m clock --check`: verify everything Clock depends on, and say what to fix."""
import asyncio
import sys

from . import config as C


def _ollama():
    from .brain import check_ollama
    problem = check_ollama()
    return (problem is None, problem or f"Ollama is up and has {C.MODEL}")


def _mic():
    import sounddevice as sd
    dev = sd.query_devices(kind="input")
    return True, f"input device: {dev['name']}"


def _whisper():
    if C.STT_ENGINE in ("auto", "phonon"):
        try:
            import fermion  # noqa: F401
            return True, "Phonon-2 (fermion-research installed; Whisper is the fallback)"
        except ImportError:
            pass
    import faster_whisper  # noqa: F401  (the model itself downloads on first use)
    return True, f"faster-whisper installed; model {C.WHISPER_MODEL} loads on first run"


def _voice():
    import edge_tts
    voices = asyncio.run(edge_tts.list_voices())
    if any(v["ShortName"] == C.VOICE for v in voices):
        return True, f"voice {C.VOICE} exists"
    return False, f"voice {C.VOICE} not found (see `edge-tts --list-voices`)"


def _eleven():
    from . import tts_eleven
    if C.TTS_ENGINE != "eleven":
        return True, "off (CLOCK_TTS=edge); edge-tts is the voice"
    if not C.ELEVEN_KEY:
        return False, "CLOCK_TTS=eleven but no ELEVENLABS_API_KEY; she will use edge-tts"
    if not C.ELEVEN_KEY.startswith("sk_"):
        return False, "the key does not start with sk_: copy the secret key (shown once when created), not the key ID"
    left = C.ELEVEN_BUDGET - tts_eleven.used()
    return True, (f"model {C.ELEVEN_MODEL}; {max(left, 0)} of {C.ELEVEN_BUDGET} budgeted characters left this month; "
                  f"account: {tts_eleven.balance()}")


def _audio_out():
    import pygame
    pygame.mixer.init()
    pygame.mixer.quit()
    return True, "audio output opens"


def _folder():
    if C.ALLOWED_DIR.is_dir():
        return True, f"file tools limited to {C.ALLOWED_DIR}"
    return False, f"{C.ALLOWED_DIR} doesn't exist (set CLOCK_DIR)"


def _wake():
    from . import wake
    models = wake.resolve_models()
    if C.WAKE_ENGINE == "whisper" or not models:
        return True, "Whisper phrase match (add models/hey_clock.onnx for openWakeWord; see docs/wake_word_training.md)"
    gate = wake.load_gate()  # also proves the model file loads
    return gate is not None, wake.describe() if gate else "model configured but could not be loaded (see message above)"


CHECKS = [("Ollama", _ollama), ("Microphone", _mic), ("Speech recognition", _whisper),
          ("Wake word", _wake), ("Voice", _voice), ("ElevenLabs", _eleven), ("Audio output", _audio_out), ("Files folder", _folder)]


def run() -> int:
    failed = 0
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        failed += not ok
        print(f"[{'ok' if ok else 'FAIL'}] {name}: {detail}")
    print("\nAll good." if not failed else f"\n{failed} problem(s) to fix.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
