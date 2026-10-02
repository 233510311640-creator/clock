import queue
import numpy as np
import sounddevice as sd
from . import config as C

_mic_dead = False


def record_utterance(max_wait=None, on_mic=None):
    """Block until speech starts, then record until silence. Returns float32 mono array or None.

    on_mic(alive) is called with False when the mic has delivered nothing but digital silence for
    MIC_SILENT_SECONDS (muted or blocked), and with True when signal returns.
    """
    global _mic_dead
    q = queue.Queue()
    block = int(C.SAMPLE_RATE * 0.05)

    def cb(indata, frames, t, status):
        q.put(indata[:, 0].copy())

    chunks, started, silent, waited, dead_for = [], False, 0.0, 0.0, 0.0
    with sd.InputStream(samplerate=C.SAMPLE_RATE, channels=1, blocksize=block, callback=cb):
        while True:
            data = q.get()
            level = float(np.sqrt(np.mean(data ** 2)))
            loud = level > C.ENERGY_THRESHOLD
            if not started and on_mic:
                if level < C.MIC_SILENT_LEVEL:
                    dead_for += 0.05
                    if dead_for >= C.MIC_SILENT_SECONDS and not _mic_dead:
                        _mic_dead = True
                        on_mic(False)
                else:
                    dead_for = 0.0
                    if _mic_dead:
                        _mic_dead = False
                        on_mic(True)
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
