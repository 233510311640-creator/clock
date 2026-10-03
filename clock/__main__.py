import argparse
import re
import time

from . import config as C
from . import reminders
from .brain import Brain, check_ollama


# What Whisper tends to write when it hears "Clock". Accepted only after a greeting, so a plain
# "click the button" or "lock the screen" doesn't wake her.
_MISHEARD = r"clark|clack|click|cluck|clok|klok|clog|glock|flock|cloak|plock|lock|o'?clock"
_GREETING = r"(?:hey|hi|hello|ok|okay|yo|hay|hiya)"
_WAKE = re.compile(
    rf"^\s*(?:{_GREETING}[, ]+)?(?:clock|klock)\b[,.!? ]*(?P<exact>.*)$"
    rf"|^\s*{_GREETING}[, ]+(?:{_MISHEARD})\b[,.!? ]*(?P<fuzzy>.*)$", re.I)


def strip_wake(text: str):
    """Return the command if text starts with a wake word, else None."""
    m = _WAKE.match(text)
    if not m:
        return None
    rest = m.group("exact") if m.group("exact") is not None else m.group("fuzzy")
    return rest.strip()


SEE_YOU = re.compile(r"\bsee you,? (?:clock|klock|clark|clack|cluck|clok|klok)\b", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", action="store_true", help="type instead of speaking (no mic needed)")
    ap.add_argument("--check", action="store_true", help="check Ollama, mic, voice and audio, then exit")
    ap.add_argument("--mute", action="store_true", help="don't speak replies")
    args = ap.parse_args()

    if args.check:
        from .check import run
        raise SystemExit(run())

    problem = check_ollama()
    if problem:
        print(f"(warning: {problem})")  # keep going: Ollama may come up later, and ask() reports it per request

    if args.text:
        def speak(t):
            print(f"Clock: {t}")

        def confirm(q):
            return input(f"{q} (y/n) ").strip().lower().startswith("y")

        brain = Brain(speak, confirm)
        reminders.start(speak)
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
    from .tts import Speaker, chime, ensure_mixer
    from .hud import Hud
    from .tray import Tray

    spk = Speaker(mute=args.mute)

    hud = Hud()

    def speak(t):
        hud.reply(t)
        spk.say(t)
        spk.wait()

    def confirm(q):
        speak(q)
        a = record_utterance(max_wait=8)
        return bool(a is not None and re.search(r"\b(yes|yeah|yep|sure|confirm|do it)\b", transcribe(a), re.I))

    brain = Brain(speak, confirm)
    tray = Tray()
    tray.start()
    hud.start()

    def set_status(text):
        tray.status(text)
        hud.status(text)

    def on_mic(alive):
        if alive:
            print("(mic signal is back)")
            set_status("listening")
            speak(f"I can hear you again{C.ADDRESS}.")
        else:
            print("(mic is silent: muted or blocked)")
            set_status("mic silent - muted?")
            speak(f"I can't hear anything{C.ADDRESS}. Your microphone looks off, muted or blocked. Is the headset on?")
    try:
        import numpy as np
        set_status("loading")
        ensure_mixer()  # so the first chime is instant
        transcribe(np.zeros(C.SAMPLE_RATE, dtype="float32"))  # warm up Whisper so the first command isn't slow
        speak(f"Clock online. Say my name when you need me{C.ADDRESS}." if not problem else
              f"Clock online, but there's a problem{C.ADDRESS}. {problem.split('. Run')[0]}.")
        reminders.start(speak)
        while True:
            set_status("listening")
            try:
                audio = record_utterance(on_mic=on_mic)
            except Exception as e:  # mic unplugged / device busy
                print(f"(mic error: {e})")
                set_status("mic unavailable")
                time.sleep(5)
                continue
            if audio is None:
                continue
            set_status("hearing you")
            t0 = time.perf_counter()
            heard = transcribe(audio)
            print(f"[heard in {time.perf_counter() - t0:.1f}s] {heard!r}")
            if not heard:
                continue
            if SEE_YOU.search(heard):
                speak(f"See you{C.ADDRESS}.")
                break
            cmd = strip_wake(heard)
            if cmd is None:
                continue  # not addressed to Clock
            chime()  # she heard her name
            if not cmd:
                set_status("waiting for your request")
                speak("Yes?")
                audio = record_utterance(max_wait=8)
                cmd = transcribe(audio) if audio is not None else ""
                if not cmd:
                    continue
            print(f"You: {cmd}")
            hud.heard(cmd)
            if re.search(r"\b(goodbye|shut down|power off)\b", cmd, re.I):
                speak("Powering down. Goodnight.")
                break
            set_status("thinking")
            t0 = time.perf_counter()
            first, said = [], []

            def on_sentence(t):
                if not first:
                    first.append(time.perf_counter() - t0)
                    print(f"[first sentence in {first[0]:.1f}s]")
                    set_status("speaking")
                said.append(t)
                hud.reply(" ".join(said))
                spk.say(t)

            brain.ask(cmd, on_sentence)
            print(f"[thought in {time.perf_counter() - t0:.1f}s]")
            spk.wait()
    finally:
        hud.stop()
        tray.stop()


if __name__ == "__main__":
    main()
