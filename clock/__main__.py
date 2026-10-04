import argparse
import contextlib
import re
import threading
import time

from . import config as C
from . import reminders, remote, routines, settings
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


# A command that ends on one of these is a sentence she cut off because you paused ("can you ...", "open ...").
_UNFINISHED = re.compile(
    r"\b(?:can|could|would|will|you|please|open|launch|start|run|close|to|the|a|an|and|my|for|in|on|with|of|then|"
    r"set|search|play|hey|hi|hello|clock)\W*$", re.I)
MAX_CONTINUATIONS = 2


def unfinished(cmd: str) -> bool:
    return bool(_UNFINISHED.search(cmd))


def join_command(cmd: str, more: str) -> str:
    """Append the continuation, dropping a repeated wake word ("... can you. Hey Clock, open Word")."""
    rest = strip_wake(more)
    return f"{cmd.rstrip(' .,!?')} {(more if rest is None else rest).strip()}".strip()


SEE_YOU = re.compile(r"\bsee you,? (?:clock|klock|clark|clack|cluck|clok|klok)\b", re.I)


def start_remote(lock, speak):
    """Start the phone channel if configured. Returns a speak() that also sends to the phone (for reminders and routines)."""
    holder = []
    brain = remote.make_brain(lambda t: holder and holder[0].send(t))
    channel = remote.from_config(lambda text: _locked_ask(lock, brain, text))
    if not channel:
        return speak
    holder.append(channel)
    channel.start()
    print(f"(phone: Telegram on, {len(channel.chats)} chat(s), tools: {'all' if remote.allowed_tools() is None else 'safe'})")

    def announce(t):
        channel.send(t)
        speak(t)
    return announce


def _locked_ask(lock, brain, text):
    with lock:  # one exchange at a time, shared with the spoken and typed ones
        return brain.ask(text)


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
        announce = start_remote(threading.Lock(), speak)
        reminders.start(announce)
        routines.start(announce)
        print("Clock online (text mode). Ctrl+C to quit.")
        while True:
            try:
                q = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q:
                speak(brain.ask(q))
        return

    from .audio import Mic, record_utterance, wait_for_wake
    from .stt import transcribe
    from .tts import Speaker, chime, ensure_mixer, plain, warm
    from .hud import Hud
    from . import convo, wake
    from .tray import Tray

    spk = Speaker(mute=args.mute)

    hud = Hud()
    gate = wake.load_gate()  # openWakeWord, or None: then every utterance is matched by Whisper
    mic = Mic() if gate else None  # the gate and the recorder share one open stream
    print(f"(wake: {wake.describe() if gate else 'Whisper phrase match'})")

    def listen(max_wait=None, silence=None):
        """Record one utterance. On the shared mic, first drop what piled up while she spoke."""
        if mic:
            mic.flush()
        return record_utterance(max_wait=max_wait, silence=silence, mic=mic)

    def speak(t):
        convo.add("clock", plain(t))
        hud.reply(plain(t))
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
    convo.reset()

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
    busy = threading.Lock()  # one exchange at a time, whether spoken or typed in the panel

    def respond(cmd):
        with busy:
            set_status("thinking")
            t0 = time.perf_counter()
            first, said = [], []

            def on_sentence(t):
                if not first:
                    first.append(time.perf_counter() - t0)
                    print(f"[first sentence in {first[0]:.1f}s]")
                    set_status("speaking")
                said.append(plain(t))
                hud.reply(" ".join(said))
                spk.say(t)

            brain.ask(cmd, on_sentence)
            convo.add("clock", " ".join(said))
            print(f"[thought in {time.perf_counter() - t0:.1f}s]")
            spk.wait()
            set_status("listening")

    applied = [None]

    def apply_settings():
        cfg = settings.load()
        if cfg != applied[0]:
            applied[0] = cfg
            hud.visible = cfg["hud"]
            spk.mute = args.mute or not cfg["voice"]
            C.CHIME = cfg["chime"]

    def watch_inbox():  # also picks up settings changed in the panel
        while True:
            apply_settings()
            for text in convo.take():
                print(f"You (typed): {text}")
                hud.heard(text)
                convo.add("you", text)
                respond(text)
            time.sleep(0.5)
    try:
        import numpy as np
        set_status("loading")
        ensure_mixer()  # so the first chime is instant
        warm()  # load the local voice (Kokoro) now, if that is the engine
        transcribe(np.zeros(C.SAMPLE_RATE, dtype="float32"))  # warm up Whisper so the first command isn't slow
        speak(f"Clock online. Say my name when you need me{C.ADDRESS}." if not problem else
              f"Clock online, but there's a problem{C.ADDRESS}. {problem.split('. Run')[0]}.")
        announce = start_remote(busy, speak)
        reminders.start(announce)
        routines.start(announce)
        apply_settings()
        convo.take()  # drop anything typed while she was off
        threading.Thread(target=watch_inbox, daemon=True, name="inbox").start()
        if mic:
            mic.open()
        while True:
            set_status("listening")
            try:
                if gate:
                    woke = wait_for_wake(mic, gate, on_mic=on_mic, busy=spk.busy)
                    set_status("hearing you")
                    print("(wake word heard)")
                    # the wake word and anything said right after it are in `woke`; carry on until you stop
                    audio = record_utterance(max_wait=10, silence=C.FOLLOWUP_SILENCE, mic=mic, initial=woke)
                else:
                    audio = record_utterance(on_mic=on_mic)
            except Exception as e:  # mic unplugged / device busy
                print(f"(mic error: {e})")
                set_status("mic unavailable")
                time.sleep(5)
                if mic:
                    with contextlib.suppress(Exception):
                        mic.open()
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
            cmd = wake.strip_trigger(heard) if gate else strip_wake(heard)
            if cmd is None:
                continue  # not addressed to Clock
            if not gate:
                chime()  # she heard her name; with the gate the orb shows it (a chime would leak into the open mic)
            if not cmd:
                set_status("waiting for your request")
                speak("Yes?")
                audio = listen(max_wait=10, silence=C.FOLLOWUP_SILENCE)
                cmd = transcribe(audio) if audio is not None else ""
                if not cmd:
                    continue
            for _ in range(MAX_CONTINUATIONS):  # she stopped mid-sentence: keep listening instead of guessing
                if not unfinished(cmd):
                    break
                set_status("waiting for your request")
                audio = listen(max_wait=6, silence=C.FOLLOWUP_SILENCE)
                more = transcribe(audio) if audio is not None else ""
                if not more:
                    break
                cmd = join_command(cmd, more)
            print(f"You: {cmd}")
            hud.heard(cmd)
            convo.add("you", cmd)
            if re.search(r"\b(goodbye|shut down|power off)\b", cmd, re.I):
                speak("Powering down. Goodnight.")
                break
            respond(cmd)
    finally:
        if mic:
            mic.close()
        hud.stop()
        tray.stop()


if __name__ == "__main__":
    main()
