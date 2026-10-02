import queue
import numpy as np
import sounddevice as sd
from . import config as C


def record_utterance(max_wait=None):
    """Block until speech starts, then record until silence. Returns float32 mono array or None."""
    q = queue.Queue()
    block = int(C.SAMPLE_RATE * 0.05)

    def cb(indata, frames, t, status):
        q.put(indata[:, 0].copy())

    chunks, started, silent, waited = [], False, 0.0, 0.0
    with sd.InputStream(samplerate=C.SAMPLE_RATE, channels=1, blocksize=block, callback=cb):
        while True:
            data = q.get()
            loud = float(np.sqrt(np.mean(data ** 2))) > C.ENERGY_THRESHOLD
            if not started:
                waited += 0.05
                if max_wait and waited > max_wait:
                    return None
                if loud:
                    started = True
                    chunks.append(data)
                continue
            chunks.append(data)
            silent = 0.0 if loud else silent + 0.05
            total = len(chunks) * 0.05
            if silent >= C.SILENCE_SECONDS or total >= C.MAX_UTTERANCE_SECONDS:
                break
    audio = np.concatenate(chunks)
    return audio if len(audio) > C.SAMPLE_RATE * 0.3 else None
