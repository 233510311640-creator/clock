import sys
import types
import wave

import numpy as np
import pytest

from clock import config as C
from clock import tts, tts_local


class FakeKokoro:
    calls = []

    def __init__(self, model, voices):
        pass

    def create(self, text, voice, speed, lang):
        FakeKokoro.calls.append((text, voice, speed, lang))
        return np.sin(np.linspace(0, 100, 2400)).astype("float32") * 0.5, 24000


@pytest.fixture(autouse=True)
def kokoro_on(tmp_path, monkeypatch):
    for name in tts_local.FILES:
        (tmp_path / name).write_bytes(b"x")
    monkeypatch.setattr(C, "TTS_ENGINE", "kokoro")
    monkeypatch.setattr(C, "KOKORO_DIR", tmp_path)
    monkeypatch.setattr(C, "KOKORO_VOICE", "bm_daniel")
    monkeypatch.setattr(C, "KOKORO_SPEED", 1.0)
    monkeypatch.setitem(sys.modules, "kokoro_onnx", types.SimpleNamespace(Kokoro=FakeKokoro))
    FakeKokoro.calls = []
    tts_local.reset()


def test_writes_a_wav_with_voice_and_language(tmp_path):
    out = tmp_path / "a.wav"
    tts_local.synthesize("Hello there", str(out))
    with wave.open(str(out)) as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1 and w.getnframes() == 2400
    assert FakeKokoro.calls == [("Hello there", "bm_daniel", 1.0, "en-gb")]


def test_american_voice_uses_us_english(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "KOKORO_VOICE", "am_adam")
    tts_local.synthesize("Hi", str(tmp_path / "a.wav"))
    assert FakeKokoro.calls[0][3] == "en-us"


def test_only_active_when_engine_is_kokoro(monkeypatch):
    assert tts_local.usable() is True
    monkeypatch.setattr(C, "TTS_ENGINE", "edge")
    assert tts_local.usable() is False


def test_missing_model_files_switch_it_off_with_instructions(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(C, "KOKORO_DIR", tmp_path / "nowhere")
    with pytest.raises(tts_local.LocalTtsError, match="download"):
        tts_local.synthesize("hi", str(tmp_path / "a.wav"))
    assert tts_local.usable() is False
    assert "download" in capsys.readouterr().out


def test_missing_package_switches_it_off(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "kokoro_onnx", None)  # makes the import raise ImportError
    with pytest.raises(tts_local.LocalTtsError, match="requirements-kokoro"):
        tts_local.synthesize("hi", str(tmp_path / "a.wav"))
    assert tts_local.usable() is False


def test_runtime_error_only_affects_that_line(tmp_path, monkeypatch):
    def boom(self, *a, **k):
        raise RuntimeError("onnx failed")
    monkeypatch.setattr(FakeKokoro, "create", boom)
    with pytest.raises(tts_local.LocalTtsError):
        tts_local.synthesize("hi", str(tmp_path / "a.wav"))
    assert tts_local.usable() is True


def test_warm_never_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "KOKORO_DIR", tmp_path / "nowhere")
    tts_local.warm()
    assert tts_local.usable() is False


def test_tts_uses_kokoro_wav_and_strips_tags(tmp_path):
    made = tts._synthesize("[whispers] Hello.", str(tmp_path / "a.mp3"))
    assert made.endswith("a.wav") and (tmp_path / "a.wav").exists()
    assert FakeKokoro.calls[0][0] == "Hello."


def test_tts_falls_back_to_edge_when_kokoro_fails(tmp_path, monkeypatch):
    spoken = []

    class FakeComm:
        def __init__(self, text, voice):
            spoken.append(text)

        async def save(self, path):
            pass
    monkeypatch.setattr(tts.edge_tts, "Communicate", FakeComm)
    monkeypatch.setattr(C, "KOKORO_DIR", tmp_path / "nowhere")
    made = tts._synthesize("Fine.", str(tmp_path / "a.mp3"))
    assert made.endswith("a.mp3") and spoken == ["Fine."]


def test_edge_engine_never_touches_kokoro(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "TTS_ENGINE", "edge")
    monkeypatch.setattr(tts.edge_tts, "Communicate",
                        lambda t, v: types.SimpleNamespace(save=lambda p: _noop()))
    tts._synthesize("Hello", str(tmp_path / "a.mp3"))
    assert FakeKokoro.calls == []


async def _noop():
    return None
