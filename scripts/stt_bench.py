"""Benchmark speech-to-text engines on short voice commands.

    python scripts/stt_bench.py synth            # make test clips with a TTS voice (smoke test only)
    python scripts/stt_bench.py record           # record your own voice reading the same commands
    python scripts/stt_bench.py run              # compare engines: word error rate + latency

Clips live in bench_clips/ (gitignored): <name>.wav (16 kHz mono) and <name>.txt (what was said).
Engines: whisper (what Clock uses now), whistle (cactus-needle), phonon (fermion-research).
Run it in a venv with the engines you want installed; missing engines are skipped.
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import uuid
import wave
from pathlib import Path

os.environ.setdefault("NEEDLE_TELEMETRY", "0")

CLIPS = Path(__file__).resolve().parent.parent / "bench_clips"
RATE = 16000
PHONON_URL = "http://127.0.0.1:8000"
HOTWORDS = ["Clock", "Notepad", "Calculator", "Chrome", "Excel", "PowerPoint", "Spotify"]

COMMANDS = [
    "hey clock",
    "what time is it",
    "open notepad",
    "open calculator",
    "close notepad",
    "turn the volume down",
    "set volume to forty",
    "mute",
    "pause the music",
    "next song",
    "what is the weather in new delhi",
    "set a timer for five minutes",
    "remind me tomorrow at eight to submit the assignment",
    "what reminders do i have",
    "remember my sister's birthday is fourteen march",
    "forget the tea thing",
    "summarise what i copied",
    "switch to chrome",
    "minimize discord",
    "snap notepad left",
    "lock the pc",
    "what is on my screen",
    "take a note buy milk and eggs",
    "search the web for the latest python release",
    "open excel",
    "how much battery do i have left",
    "clock goodbye",
    "who won the cricket match yesterday",
    "read my notes",
    "minimize everything",
]


def _slug(i, text):
    return f"{i:02d}_" + re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]


def _write_wav(path, samples):
    import numpy as np
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def _read_wav(path):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == RATE and w.getnchannels() == 1, f"{path}: need 16 kHz mono"
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768


# ---------- clip creation ----------

def cmd_synth(args):
    """Clips from edge-tts voices. Clean studio-like speech: a smoke test, not a real accuracy measure."""
    import edge_tts
    CLIPS.mkdir(exist_ok=True)
    voices = args.voice or ["en-IN-PrabhatNeural", "en-GB-RyanNeural"]
    for i, text in enumerate(COMMANDS):
        voice = voices[i % len(voices)]
        mp3 = CLIPS / "_tmp.mp3"
        asyncio.run(edge_tts.Communicate(text, voice).save(str(mp3)))
        wav = CLIPS / f"{_slug(i, text)}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", str(RATE), str(wav)], check=True)
        mp3.unlink()
        (CLIPS / f"{wav.stem}.txt").write_text(text, encoding="utf-8")
        print(f"{wav.name}  ({voice})")


def cmd_record(args):
    import numpy as np
    import sounddevice as sd
    CLIPS.mkdir(exist_ok=True)
    print("Read each line aloud when prompted. Enter = record, s = skip, q = quit.\n")
    for i, text in enumerate(COMMANDS):
        wav = CLIPS / f"{_slug(i, text)}.wav"
        if wav.exists() and not args.redo:
            continue
        ans = input(f'[{i + 1}/{len(COMMANDS)}] "{text}"  > ').strip().lower()
        if ans == "q":
            break
        if ans == "s":
            continue
        audio = sd.rec(int(args.seconds * RATE), samplerate=RATE, channels=1, dtype="float32")
        sd.wait()
        audio = audio[:, 0]
        loud = np.where(np.abs(audio) > 0.01)[0]  # trim leading/trailing silence
        if len(loud):
            audio = audio[max(0, loud[0] - 2000): loud[-1] + 4000]
        _write_wav(wav, audio)
        (CLIPS / f"{wav.stem}.txt").write_text(text, encoding="utf-8")


# ---------- engines ----------

class Whisper:
    name = "whisper"

    def __init__(self, model="small.en"):
        from faster_whisper import WhisperModel
        self.m = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=8)
        self.prompt = "Clock. Hey Clock. Open " + ", ".join(HOTWORDS) + ". What time is it? Set a timer."

    def __call__(self, wav):
        segs, _ = self.m.transcribe(_read_wav(wav), language="en", beam_size=5, vad_filter=True,
                                    initial_prompt=self.prompt, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segs).strip()


class Whistle:
    name = "whistle"

    def __init__(self):
        import needle
        self.n = needle

    def __call__(self, wav):
        return self.n.transcribe(_read_wav(wav), language="en", keywords=HOTWORDS)["text"].strip()


class Phonon:
    """Talks to `phonon serve` (starts one if none is running) so the model loads once."""
    name = "phonon"

    def __init__(self):
        self.proc = None
        if not self._up():
            exe = Path(sys.executable).with_name("phonon.exe")
            self.proc = subprocess.Popen([str(exe), "serve", "--port", "8000"],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(120):
                if self._up():
                    break
                time.sleep(1)
            else:
                raise RuntimeError("phonon serve did not start")

    def _up(self):
        try:
            urllib.request.urlopen(PHONON_URL + "/v1/models", timeout=2)
            return True
        except Exception:
            return False

    def __call__(self, wav):
        boundary = uuid.uuid4().hex
        body = b""
        for k, v in (("model", "phonon-2"), ("response_format", "json")):
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
                 f'Content-Type: audio/wav\r\n\r\n').encode() + Path(wav).read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(PHONON_URL + "/v1/audio/transcriptions", body,
                                     {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        return json.load(urllib.request.urlopen(req, timeout=60))["text"].strip()

    def close(self):
        if self.proc:
            self.proc.terminate()


# ---------- scoring ----------

_NUM = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
        "8": "eight", "9": "nine", "10": "ten", "40": "forty", "14": "fourteen",
        "fourteenth": "fourteen", "summarize": "summarise", "minimise": "minimize"}


def norm(s):
    s = s.lower().replace("-", " ")
    s = re.sub(r"[^a-z0-9' ]", " ", s)
    return [_NUM.get(w, w) for w in s.split()]


def wer_counts(ref, hyp):
    """Word-level edit distance. Returns (errors, reference length)."""
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)], len(r)


def cmd_run(args):
    wavs = sorted(CLIPS.glob("*.wav"))
    if not wavs:
        sys.exit("No clips. Run `synth` or `record` first.")
    engines = []
    for cls in (Whisper, Whistle, Phonon):
        if args.engine and cls.name not in args.engine:
            continue
        try:
            engines.append(cls())
        except Exception as e:
            print(f"skip {cls.name}: {type(e).__name__}: {e}")
    if not engines:
        sys.exit("No engines available.")
    stats = {e.name: {"err": 0, "words": 0, "times": [], "exact": 0} for e in engines}
    for e in engines:  # warm-up: first call includes lazy init
        try:
            e(wavs[0])
        except Exception as ex:
            print(f"warm-up {e.name} failed: {ex}")
    for wav in wavs:
        ref = wav.with_suffix(".txt").read_text(encoding="utf-8").strip()
        print(f"\nREF  {ref}")
        for e in engines:
            t = time.perf_counter()
            try:
                hyp = e(wav)
            except Exception as ex:
                hyp = ""
                print(f"  {e.name:8} ERROR {ex}")
            dt = (time.perf_counter() - t) * 1000
            err, n = wer_counts(ref, hyp)
            s = stats[e.name]
            s["err"] += err
            s["words"] += n
            s["times"].append(dt)
            s["exact"] += err == 0
            mark = "  " if err == 0 else "x "
            print(f"  {mark}{e.name:8} {dt:7.0f} ms  {hyp}")
    print(f"\n{'engine':8} {'WER':>7} {'exact':>9} {'median ms':>10} {'p90 ms':>8}")
    for name, s in stats.items():
        ts = sorted(s["times"])
        print(f"{name:8} {100 * s['err'] / max(1, s['words']):6.1f}% {s['exact']:>4}/{len(ts):<4} "
              f"{ts[len(ts) // 2]:10.0f} {ts[int(len(ts) * 0.9)]:8.0f}")
    for e in engines:
        if hasattr(e, "close"):
            e.close()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("synth")
    s.add_argument("--voice", action="append", help="edge-tts voice (repeatable)")
    r = sub.add_parser("record")
    r.add_argument("--seconds", type=float, default=5.0)
    r.add_argument("--redo", action="store_true")
    b = sub.add_parser("run")
    b.add_argument("--engine", action="append", choices=["whisper", "whistle", "phonon"])
    args = p.parse_args()
    {"synth": cmd_synth, "record": cmd_record, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
