import io
import json
import urllib.error

import pytest

from clock import config as C
from clock import tts, tts_eleven

AUDIO = b"ID3" + b"\x00" * 400


@pytest.fixture(autouse=True)
def eleven_on(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "TTS_ENGINE", "eleven")
    monkeypatch.setattr(C, "ELEVEN_KEY", "SECRETKEY")
    monkeypatch.setattr(C, "ELEVEN_VOICE", "voice123")
    monkeypatch.setattr(C, "ELEVEN_MODEL", "eleven_v4_turbo")
    monkeypatch.setattr(C, "ELEVEN_MAX_CHARS", 100)
    monkeypatch.setattr(C, "ELEVEN_BUDGET", 50)
    monkeypatch.setattr(C, "ELEVEN_USAGE_FILE", tmp_path / "usage.json")
    tts_eleven.reset()


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code):
    return urllib.error.HTTPError("https://api.elevenlabs.io/x", code, "err", {}, io.BytesIO(b""))


def test_request_shape_and_usage(monkeypatch, tmp_path):
    seen = {}

    def fake(req, timeout):
        seen["url"], seen["headers"], seen["body"] = req.full_url, dict(req.header_items()), json.loads(req.data)
        return Resp(AUDIO)
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", fake)
    out = tmp_path / "a.mp3"
    tts_eleven.synthesize("Hello there", str(out))
    assert out.read_bytes() == AUDIO
    assert seen["url"].startswith("https://api.elevenlabs.io/v1/text-to-speech/voice123?output_format=mp3_44100_128")
    assert seen["headers"]["Xi-api-key"] == "SECRETKEY"
    assert seen["body"] == {"text": "Hello there", "model_id": "eleven_v4_turbo"}
    assert tts_eleven.used() == len("Hello there")


def test_usable_respects_engine_key_length_and_budget():
    assert tts_eleven.usable("short") is True
    assert tts_eleven.usable("x" * 101) is False                 # too long: edge-tts instead
    assert tts_eleven.usable("x" * 51) is False                  # over the budget of 50
    C.TTS_ENGINE = "edge"
    assert tts_eleven.usable("short") is False
    C.TTS_ENGINE, C.ELEVEN_KEY = "eleven", ""
    assert tts_eleven.usable("short") is False


def test_budget_runs_out_across_calls(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", lambda req, timeout: Resp(AUDIO))
    for _ in range(2):
        tts_eleven.synthesize("x" * 20, str(tmp_path / "a.mp3"))
    assert tts_eleven.used() == 40
    assert tts_eleven.usable("x" * 11) is False and tts_eleven.usable("x" * 10) is True


def test_usage_resets_in_a_new_month(monkeypatch):
    C.ELEVEN_USAGE_FILE.write_text(json.dumps({"month": "1999-01", "chars": 9999}))
    assert tts_eleven.used() == 0


@pytest.mark.parametrize("code", [401, 402])
def test_key_or_credit_errors_switch_it_off_for_the_session(monkeypatch, tmp_path, code):
    def fake(req, timeout):
        raise http_error(code)
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", fake)
    with pytest.raises(tts_eleven.ElevenError):
        tts_eleven.synthesize("hi", str(tmp_path / "a.mp3"))
    assert tts_eleven.usable("hi") is False


def test_rate_limit_only_skips_that_line(monkeypatch, tmp_path):
    def fake(req, timeout):
        raise http_error(429)
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", fake)
    with pytest.raises(tts_eleven.ElevenError):
        tts_eleven.synthesize("hi", str(tmp_path / "a.mp3"))
    assert tts_eleven.usable("hi") is True


def test_three_network_failures_switch_it_off(monkeypatch, tmp_path):
    def fake(req, timeout):
        raise urllib.error.URLError("down")
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", fake)
    for _ in range(tts_eleven.MAX_FAILS):
        with pytest.raises(tts_eleven.ElevenError):
            tts_eleven.synthesize("hi", str(tmp_path / "a.mp3"))
    assert tts_eleven.usable("hi") is False


def test_key_never_appears_in_errors(monkeypatch, tmp_path):
    def fake(req, timeout):
        raise urllib.error.URLError("SECRETKEY leaked in message")
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", fake)
    with pytest.raises(tts_eleven.ElevenError) as e:
        tts_eleven.synthesize("hi", str(tmp_path / "a.mp3"))
    assert "SECRETKEY" not in str(e.value) and "SECRETKEY" not in repr(e.value.__cause__)


def test_tiny_response_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", lambda req, timeout: Resp(b"{}"))
    with pytest.raises(tts_eleven.ElevenError):
        tts_eleven.synthesize("hi", str(tmp_path / "a.mp3"))


def test_plain_strips_audio_tags():
    assert tts_eleven.plain("[whispers] Closer now. [laughs] Okay.") == "Closer now. Okay."
    assert tts_eleven.plain("Items [1] and [2]") == "Items and"
    assert tts_eleven.plain("no tags") == "no tags"


def test_synthesize_falls_back_to_edge_with_plain_text(monkeypatch, tmp_path):
    spoken = []

    class FakeComm:
        def __init__(self, text, voice):
            spoken.append(text)

        async def save(self, path):
            pass
    monkeypatch.setattr(tts.edge_tts, "Communicate", FakeComm)

    def fail(req, timeout):
        raise urllib.error.URLError("down")
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", fail)
    tts._synthesize("[sighs] Fine.", str(tmp_path / "a.mp3"))
    assert spoken == ["Fine."]


def test_synthesize_uses_eleven_when_usable(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", lambda req, timeout: Resp(AUDIO))
    monkeypatch.setattr(tts.edge_tts, "Communicate", lambda *a: pytest.fail("edge used"))
    out = tmp_path / "a.mp3"
    tts._synthesize("[whispers] Hi.", str(out))
    assert out.read_bytes() == AUDIO


def test_edge_engine_never_calls_eleven(monkeypatch, tmp_path):
    C.TTS_ENGINE = "edge"
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network"))
    spoken = []

    class FakeComm:
        def __init__(self, text, voice):
            spoken.append(text)

        async def save(self, path):
            pass
    monkeypatch.setattr(tts.edge_tts, "Communicate", FakeComm)
    tts._synthesize("Hello", str(tmp_path / "a.mp3"))
    assert spoken == ["Hello"]


def test_key_id_instead_of_secret_switches_off_with_clear_reason(monkeypatch, tmp_path, capsys):
    body = b'{"detail":{"code":"invalid_api_key","status":"api_key_id_used_as_api_key"}}'

    def fake(req, timeout):
        raise urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(body))
    monkeypatch.setattr(tts_eleven.urllib.request, "urlopen", fake)
    with pytest.raises(tts_eleven.ElevenError):
        tts_eleven.synthesize("hi", str(tmp_path / "a.mp3"))
    assert tts_eleven.usable("hi") is False
    assert "sk_" in capsys.readouterr().out
