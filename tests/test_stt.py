import numpy as np

from clock import config as C
from clock import stt


def _reset(monkeypatch, engine):
    monkeypatch.setattr(C, "STT_ENGINE", engine)
    monkeypatch.setattr(stt, "_phonon_failed", False)
    monkeypatch.setattr(stt, "_transcribe_whisper", lambda a: "whisper")


def test_phonon_used_when_available(monkeypatch):
    _reset(monkeypatch, "auto")
    monkeypatch.setattr(stt, "_transcribe_phonon", lambda a: "phonon")
    assert stt.transcribe(np.zeros(10, dtype="float32")) == "phonon"


def test_whisper_engine_never_loads_phonon(monkeypatch):
    _reset(monkeypatch, "whisper")

    def boom(a):
        raise AssertionError("phonon must not load")
    monkeypatch.setattr(stt, "_transcribe_phonon", boom)
    assert stt.transcribe(np.zeros(10, dtype="float32")) == "whisper"


def test_phonon_error_falls_back_for_good(monkeypatch):
    _reset(monkeypatch, "auto")
    calls = []

    def boom(a):
        calls.append(1)
        raise ImportError("fermion missing")
    monkeypatch.setattr(stt, "_transcribe_phonon", boom)
    audio = np.zeros(10, dtype="float32")
    assert stt.transcribe(audio) == "whisper"
    assert stt.transcribe(audio) == "whisper"
    assert len(calls) == 1  # not retried after the first failure
