import queue

import numpy as np

from clock import audio, config as C, wake

BLOCK = audio.FRAME


class FakeMic:
    block = BLOCK

    def __init__(self, levels):
        self.q = queue.Queue()
        for lvl in levels:
            self.q.put(np.full(BLOCK, lvl, dtype="float32"))
        self.flushed = 0

    def flush(self):
        self.flushed += 1

    def get(self, timeout=2):
        try:
            return self.q.get_nowait()
        except queue.Empty:
            raise RuntimeError("end of audio")


class FakeGate:
    """Fires on any block whose level is 0.5; records what it was shown."""
    threshold = 0.5

    def __init__(self):
        self.resets, self.seen = 0, 0

    def reset(self):
        self.resets += 1

    def score(self, frame):
        self.seen += 1
        return 1.0 if frame.max() > 15000 else 0.0


def test_wait_for_wake_returns_recent_audio():
    mic = FakeMic([0.0] * 30 + [0.01] * 3 + [0.6])
    woke = audio.wait_for_wake(mic, FakeGate(), keep=1.2)
    assert len(woke) == round(1.2 / (BLOCK / C.SAMPLE_RATE))  # ring is full
    assert woke[-1].max() == np.float32(0.6)  # ends on the block that fired
    assert mic.flushed == 1


def test_her_own_voice_never_wakes_her():
    speaking = [True] * 5 + [False] * 100
    mic, gate = FakeMic([0.6] * 5 + [0.0] * 8 + [0.6]), FakeGate()
    calls = iter(speaking)
    woke = audio.wait_for_wake(mic, gate, busy=lambda: next(calls, False), settle=0.5)
    # 5 loud blocks while busy + a 0.5 s settle (7 blocks) are never shown to the gate; only what follows is
    assert woke[-1].max() == np.float32(0.6)
    assert gate.seen == len(woke) == 2
    assert gate.resets >= 2  # reset at start and again after she stopped talking


def test_record_continues_from_initial_audio():
    initial = [np.full(BLOCK, 0.1, dtype="float32")] * 3
    mic = FakeMic([0.1] * 5 + [0.0] * 40)
    out = audio.record_utterance(max_wait=5, silence=1.0, mic=mic, initial=initial)
    assert out is not None and len(out) >= 8 * BLOCK  # initial + the speech that followed


def test_record_gives_up_when_nothing_follows(monkeypatch):
    mic = FakeMic([0.0] * 200)
    assert audio.record_utterance(max_wait=1.0, mic=mic) is None


def test_trailing_quiet_in_initial_counts_toward_silence():
    initial = [np.full(BLOCK, 0.1, dtype="float32")] + [np.zeros(BLOCK, dtype="float32")] * 20  # ~1.6 s quiet
    mic = FakeMic([0.0] * 5)
    out = audio.record_utterance(silence=1.0, mic=mic, initial=initial)
    assert out is not None and len(out) == (len(initial) + 1) * BLOCK  # ended on the first block, no long wait


def test_strip_trigger_follows_the_model_phrase(monkeypatch):
    monkeypatch.setattr(C, "WAKE_MODEL", "models/hey_clock.onnx")
    assert wake.strip_trigger("Hey, Clark. Open Word.") == "Open Word."
    assert wake.strip_trigger("Hey Clock") == ""
    assert wake.strip_trigger("Hey.") == ""
    assert wake.strip_trigger("open word") == "open word"
    monkeypatch.setattr(C, "WAKE_MODEL", "hey_jarvis")
    assert wake.strip_trigger("Hey Jarvis, open Word") == "open Word"


def test_trigger_words_from_filenames():
    assert wake.trigger_words(["a/b/hey_jarvis_v0.1.onnx"]) == ("hey", "jarvis")
    assert wake.trigger_words(["hey_clock.onnx"]) == ("hey", "clock")
    assert wake.trigger_words([]) == ("clock",)


def test_engine_falls_back_to_whisper(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(wake, "DEFAULT_MODEL", tmp_path / "none.onnx")
    monkeypatch.setattr(C, "WAKE_MODEL", "")
    monkeypatch.setattr(C, "WAKE_ENGINE", "auto")
    assert wake.load_gate() is None and "Whisper" in wake.describe()
    monkeypatch.setattr(C, "WAKE_MODEL", str(tmp_path / "missing.onnx"))
    assert wake.load_gate() is None
    assert "not found" in capsys.readouterr().out
    monkeypatch.setattr(C, "WAKE_ENGINE", "whisper")
    assert wake.load_gate() is None


def test_default_model_is_picked_up(monkeypatch, tmp_path):
    f = tmp_path / "hey_clock.onnx"
    f.write_bytes(b"x")
    monkeypatch.setattr(wake, "DEFAULT_MODEL", f)
    monkeypatch.setattr(C, "WAKE_MODEL", "")
    assert wake.resolve_models() == [str(f)]
