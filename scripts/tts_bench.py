"""Compare text-to-speech engines on Clock-style replies: speed and sound.

    python scripts/tts_bench.py [--models DIR] [--out DIR]

DIR holds kokoro-v1.0.onnx, voices-v1.0.bin and Piper voices (*.onnx + *.onnx.json). Missing engines are skipped.
Writes one wav per engine/voice/line to --out so you can listen. Prints seconds to generate and real-time factor
(RTF = generation time / audio length; below 1 means faster than speech).
"""
import argparse
import asyncio
import statistics
import subprocess
import tempfile
import time
import wave
from pathlib import Path

LINES = [
    "It's ten forty five.",
    "Notepad is open.",
    "Reminder set for tomorrow at eight.",
    "Delhi, India: thirty one degrees, hazy, humidity sixty percent. Today: high thirty four, low twenty six.",
    "I found three results. The first says the latest Python release is three point fourteen, out since October.",
    "Sorry, I couldn't reach the weather service. Try again in a minute.",
]
EDGE_VOICE = "en-GB-RyanNeural"


def write_wav(path, samples, rate):
    import numpy as np
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def run_engine(name, synth, out: Path, results):
    """synth(text) -> (float32 samples, rate). Warm-up call first so model load is not counted."""
    synth("Warm up.")
    gen, audio = [], []
    for i, line in enumerate(LINES):
        t = time.perf_counter()
        samples, rate = synth(line)
        gen.append(time.perf_counter() - t)
        audio.append(len(samples) / rate)
        write_wav(out / f"{name}_{i}.wav", samples, rate)
    results.append((name, statistics.median(gen), max(gen), sum(gen) / sum(audio)))


def kokoro_engines(models: Path):
    model, voices = models / "kokoro-v1.0.onnx", models / "voices-v1.0.bin"
    if not (model.exists() and voices.exists()):
        print("skip kokoro: model files not found")
        return
    from kokoro_onnx import Kokoro
    k = Kokoro(str(model), str(voices))
    for v in ("bm_george", "bm_daniel", "bm_lewis", "am_adam"):
        lang = "en-gb" if v.startswith("b") else "en-us"
        yield f"kokoro-{v}", lambda t, v=v, lang=lang: k.create(t, voice=v, speed=1.0, lang=lang)


def piper_engines(models: Path):
    files = sorted(models.glob("*.onnx"))
    files = [f for f in files if f.with_suffix(".onnx.json").exists() and not f.name.startswith("kokoro")]
    if not files:
        print("skip piper: no voices found")
        return
    import numpy as np
    from piper import PiperVoice
    for f in files:
        voice = PiperVoice.load(str(f))

        def synth(text, voice=voice):
            chunks = list(voice.synthesize(text))
            audio = np.concatenate([c.audio_int16_array for c in chunks]).astype("float32") / 32768
            return audio, chunks[0].sample_rate
        yield f"piper-{f.stem}", synth


def edge_engine():
    try:
        import edge_tts
    except ImportError:
        print("skip edge: edge-tts not installed")
        return None

    def synth(text):
        with tempfile.TemporaryDirectory() as d:
            mp3, wav = Path(d, "a.mp3"), Path(d, "a.wav")
            asyncio.run(edge_tts.Communicate(text, EDGE_VOICE).save(str(mp3)))
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", "24000", str(wav)],
                           check=True)
            import numpy as np
            with wave.open(str(wav)) as w:
                return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768, w.getframerate()
    return f"edge-{EDGE_VOICE}", synth


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=".", help="folder with Kokoro and Piper model files")
    ap.add_argument("--out", default="tts_out")
    args = ap.parse_args()
    models, out = Path(args.models), Path(args.out)
    out.mkdir(exist_ok=True)
    results = []
    engines = list(kokoro_engines(models)) + list(piper_engines(models))
    edge = edge_engine()
    if edge:
        engines.append(edge)
    for name, synth in engines:
        print(f"running {name} ...")
        run_engine(name, synth, out, results)
    print(f"\n{'engine':46} {'median s':>9} {'worst s':>8} {'RTF':>6}")
    for name, med, worst, rtf in results:
        print(f"{name:46} {med:9.2f} {worst:8.2f} {rtf:6.2f}")
    print(f"\nListen: files in {out.resolve()}  (…_0.wav short … _3.wav long)")


if __name__ == "__main__":
    main()
