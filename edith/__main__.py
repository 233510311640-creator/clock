import argparse
import re
import time

from . import config as C
from .brain import Brain


def strip_wake(text: str):
    """Return the command if text starts with a wake word, else None."""
    m = re.match(r"^\s*((hey|hi|hello|ok|okay)[, ]+)?(clock|klock)\b[,.!? ]*(.*)$", text, re.I)
    return m.group(4).strip() if m else None


SEE_YOU = re.compile(r"\bsee you,? (clock|klock)\b", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", action="store_true", help="type instead of speaking (no mic needed)")
    ap.add_argument("--mute", action="store_true", help="don't speak replies")
    args = ap.parse_args()

    if args.text:
        def speak(t):
            print(f"Clock: {t}")

        def confirm(q):
            return input(f"{q} (y/n) ").strip().lower().startswith("y")

        brain = Brain(speak, confirm)
        print("Clock online (text mode). Ctrl+C to quit.")
        while True:
            try:
                q = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q:
                speak(brain.ask(q))
        return

    from .audio import record_utterance
    from .stt import transcribe
    from .tts import speak as _speak
    from .tray import Tray

    def _print(t):
        print(f"Clock: {t}")

    speak = _print if args.mute else _speak

    def confirm(q):
        speak(q)
        a = record_utterance(max_wait=8)
        return bool(a is not None and re.search(r"\b(yes|yeah|yep|sure|confirm|do it)\b", transcribe(a), re.I))

    brain = Brain(speak, confirm)
    tray = Tray()
    tray.start()
    try:
        import numpy as np
        tray.status("loading")
        transcribe(np.zeros(C.SAMPLE_RATE, dtype="float32"))  # warm up Whisper so the first command isn't slow
        speak(f"Clock online. Say my name when you need me, {C.USER_NAME}.")
        while True:
            tray.status("listening")
            audio = record_utterance()
            if audio is None:
                continue
            tray.status("hearing you")
            t0 = time.perf_counter()
            heard = transcribe(audio)
            print(f"[heard in {time.perf_counter() - t0:.1f}s] {heard!r}")
            if not heard:
                continue
            if SEE_YOU.search(heard):
                speak(f"See you, {C.USER_NAME}.")
                break
            cmd = strip_wake(heard)
            if cmd is None:
                continue  # not addressed to Clock
            if not cmd:
                tray.status("waiting for your request")
                speak("Yes?")
                audio = record_utterance(max_wait=8)
                cmd = transcribe(audio) if audio is not None else ""
                if not cmd:
                    continue
            print(f"You: {cmd}")
            if re.search(r"\b(goodbye|shut down|power off)\b", cmd, re.I):
                speak("Powering down. Goodnight.")
                break
            tray.status("thinking")
            t0 = time.perf_counter()
            answer = brain.ask(cmd)
            print(f"[thought in {time.perf_counter() - t0:.1f}s]")
            tray.status("speaking")
            speak(answer)
    finally:
        tray.stop()


if __name__ == "__main__":
    main()
