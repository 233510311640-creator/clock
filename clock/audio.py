import collections
import contextlib
import queue
import numpy as np
import sounddevice as sd
from . import config as C

_mic_dead = False
FRAME = 1280  # 80 ms at 16 kHz: openWakeWord's native step


class Mic:
    """One input stream that stays open, shared by wake-word detection and recording.

    Reopening a stream between the wake word and the command would drop the first words of the command.
    """
    block = FRAME

    def __init__(self):
        self.q = queue.Queue()
        self.stream = None

    def _cb(self, indata, frames, t, status):
        self.q.put(indata[:, 0].copy())

    def open(self):
        self.close()
        self.flush()
        self.stream = sd.InputStream(samplerate=C.SAMPLE_RATE, channels=1, blocksize=self.block, callback=self._cb)
        self.stream.start()

    def close(self):
        if self.stream is not None:
            with contextlib.suppress(Exception):
                self.stream.stop()
                self.stream.close()
            self.stream = None

    def alive(self) -> bool:
        return self.stream is not None and self.stream.active

    def flush(self):
        """Drop audio captured so far (her own voice, a chime) so it isn't mistaken for you."""
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass

    def get(self, timeout=2.0):
        """Next block; raises if the device stopped delivering (unplugged, taken by another program)."""
        while True:
            try:
                return self.q.get(timeout=timeout)
            except queue.Empty:
                if not self.alive():
                    raise RuntimeError("microphone stream stopped")


class _MicWatch:
    """Calls on_mic(False) after MIC_SILENT_SECONDS of digital silence and on_mic(True) when signal returns."""

    def __init__(self, on_mic):
        self.on_mic, self.dead_for = on_mic, 0.0

    def feed(self, level: float, dt: float):
        global _mic_dead
        if not self.on_mic:
            return
        if level < C.MIC_SILENT_LEVEL:
            self.dead_for += dt
            if self.dead_for >= C.MIC_SILENT_SECONDS and not _mic_dead:
                _mic_dead = True
                self.on_mic(False)
        else:
            self.dead_for = 0.0
            if _mic_dead:
                _mic_dead = False
                self.on_mic(True)


def _rms(data) -> float:
    return float(np.sqrt(np.mean(data ** 2)))


def record_utterance(max_wait=None, on_mic=None, silence=None, mic=None, initial=None):
    """Block until speech starts, then record until `silence` seconds of quiet (default SILENCE_SECONDS).
    Returns float32 mono array or None.

    on_mic(alive) is called with False when the mic has delivered nothing but digital silence for
    MIC_SILENT_SECONDS (muted or blocked), and with True when signal returns.
    mic: read from this open Mic instead of opening a stream. initial: blocks already heard (the wake word
    and whatever followed it); recording continues from them instead of waiting for speech to start.
    """
    silence = C.SILENCE_SECONDS if silence is None else silence
    block = mic.block if mic else int(C.SAMPLE_RATE * 0.05)
    dt = block / C.SAMPLE_RATE
    pre = collections.deque(maxlen=max(1, round(C.PRE_ROLL_SECONDS / dt)))
    chunks, started, silent, waited = [], False, 0.0, 0.0
    watch = _MicWatch(on_mic)
    if initial:
        started = True
        chunks.extend(initial)
        for d in reversed(initial):  # quiet at the tail counts toward the end-of-speech timer
            if _rms(d) > C.ENERGY_THRESHOLD:
                break
            silent += dt

    q = mic.q if mic else queue.Queue()
    stream = contextlib.nullcontext() if mic else sd.InputStream(
        samplerate=C.SAMPLE_RATE, channels=1, blocksize=block, callback=lambda indata, f, t, s: q.put(indata[:, 0].copy()))
    with stream:
        while True:
            data = mic.get() if mic else q.get()
            level = _rms(data)
            loud = level > C.ENERGY_THRESHOLD
            if not started:
                watch.feed(level, dt)
                waited += dt
                if max_wait and waited > max_wait:
                    return None
                if loud:
                    started = True
                    chunks.extend(pre)
                    chunks.append(data)
                else:
                    pre.append(data)
                continue
            chunks.append(data)
            silent = 0.0 if loud else silent + dt
            total = len(chunks) * dt
            if silent >= silence or total >= C.MAX_UTTERANCE_SECONDS:
                break
    audio = np.concatenate(chunks)
    return audio if len(audio) > C.SAMPLE_RATE * 0.3 else None


def wait_for_wake(mic, gate, on_mic=None, busy=None, keep=1.2, settle=0.5):
    """Block until the wake-word gate fires. Returns the last `keep` seconds of audio, which holds the wake
    word and the start of any command spoken straight after it.

    busy(): True while she is speaking. Those blocks are skipped (and for `settle` seconds after) so her own
    voice, which may contain the word "clock", never wakes her.
    """
    dt = mic.block / C.SAMPLE_RATE
    ring = collections.deque(maxlen=max(1, round(keep / dt)))
    watch = _MicWatch(on_mic)
    mic.flush()
    gate.reset()
    quiet_for, skipping = 0.0, False
    while True:
        data = mic.get()
        watch.feed(_rms(data), dt)
        if busy and busy():
            ring.clear()
            quiet_for, skipping = settle, True
            continue
        if quiet_for > 0:
            quiet_for -= dt
            ring.clear()
            continue
        if skipping:
            gate.reset()  # model state still holds her voice
            skipping = False
        ring.append(data)
        if gate.score((np.clip(data, -1, 1) * 32767).astype(np.int16)) >= gate.threshold:
            return list(ring)
