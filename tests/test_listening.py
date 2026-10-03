import numpy as np

from clock import audio, config as C
from clock.__main__ import join_command, unfinished
from clock.tools import APPS

BLOCK = int(C.SAMPLE_RATE * 0.05)


def test_unfinished_sentences():
    assert unfinished("Can you.")
    assert unfinished("Hello Clock. Can you")
    assert unfinished("open")
    assert not unfinished("Open Word")
    assert not unfinished("What time is it?")
    assert not unfinished("begin")  # ends in "in" but not as a word


def test_join_drops_repeated_wake_word():
    assert join_command("Can you.", "open Word") == "Can you open Word"
    assert join_command("Can you.", "Hey Clock, open Word") == "Can you open Word"


def test_office_apps_allowed():
    assert {"word", "excel", "powerpoint"} <= set(APPS)


def _record(monkeypatch, plan, **kw):
    """plan: list of (seconds, level). Feeds fake 50 ms blocks to record_utterance."""
    blocks = [np.full((BLOCK, 1), lvl, dtype="float32") for sec, lvl in plan for _ in range(round(sec / 0.05))]

    class Fake:
        def __init__(self, samplerate, channels, blocksize, callback):
            self.cb = callback

        def __enter__(self):
            for b in blocks:
                self.cb(b, BLOCK, None, None)
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(audio.sd, "InputStream", Fake)
    return audio.record_utterance(**kw)


def test_mid_sentence_pause_does_not_end_capture(monkeypatch):
    # "can you" - 0.6 s thinking pause - "open word" - long quiet
    out = _record(monkeypatch, [(0.5, 0.0), (0.4, 0.1), (0.6, 0.0), (0.5, 0.1), (1.5, 0.0)])
    assert out is not None and len(out) / C.SAMPLE_RATE > 1.5  # both bursts captured


def test_long_pause_still_ends_capture(monkeypatch):
    out = _record(monkeypatch, [(0.4, 0.1), (1.2, 0.0), (0.5, 0.1), (1.5, 0.0)])
    assert out is not None and len(out) / C.SAMPLE_RATE < 1.9  # second burst is a new utterance


def test_pre_roll_keeps_the_first_word(monkeypatch):
    out = _record(monkeypatch, [(1.0, 0.0), (0.4, 0.1), (1.5, 0.0)])
    assert out is not None and len(out) / C.SAMPLE_RATE >= 0.4 + C.PRE_ROLL_SECONDS
