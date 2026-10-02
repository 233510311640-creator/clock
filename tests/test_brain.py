import json
import urllib.error

from edith import brain
from edith.brain import _NEEDS_TOOL, _Sentences, explain_error, trim_history


def test_needs_tool_matches_commands():
    for text in ["remind me at 8 to call mum", "what's the weather", "close chrome",
                 "please lock the PC", "can you mute it", "snap notepad left", "copy see you at five"]:
        assert _NEEDS_TOOL.search(text), text


def test_needs_tool_ignores_chat():
    for text in ["tell me a joke", "who wrote Hamlet", "is the shop close by", "how are you"]:
        assert not _NEEDS_TOOL.search(text), text


def test_sentences_split_across_deltas():
    out = []
    s = _Sentences(out.append)
    for d in ["Hello the", "re. How are", " you? Fine", "."]:
        s.feed(d)
    assert out == ["Hello there.", "How are you?"]
    s.flush()
    assert out[-1] == "Fine."


def test_sentences_flush_empty():
    out = []
    s = _Sentences(out.append)
    s.feed("   ")
    s.flush()
    assert out == []


def _u(t): return {"role": "user", "content": t}
def _a(t): return {"role": "assistant", "content": t}


def test_trim_by_count_starts_at_user():
    h = [m for i in range(20) for m in (_u(f"q{i}"), _a(f"a{i}"))]
    out = trim_history(h, max_msgs=7)
    assert len(out) <= 7 and out[0]["role"] == "user"
    assert out[-1] == h[-1]


def test_trim_by_size_drops_oldest_large_tool_output():
    h = [_u("q1"), {"role": "tool", "content": "x" * 5000}, _a("a1"), _u("q2"), _a("a2")]
    out = trim_history(h, max_chars=1000)
    assert out == [_u("q2"), _a("a2")]


def test_trim_never_starts_with_image_turn():
    img = {"role": "user", "content": "look", "images": ["b64"]}
    out = trim_history([_u("a"), img, _a("seen"), _u("b")], max_msgs=3)
    assert out == [_u("b")]


def test_trim_empty():
    assert trim_history([]) == []


def test_explain_error():
    assert "isn't running" in explain_error(urllib.error.URLError(ConnectionRefusedError()))
    assert "ollama pull" in explain_error(urllib.error.HTTPError("u", 404, "nf", {}, None))
    assert "too long" in explain_error(TimeoutError())
    assert "too long" in explain_error(urllib.error.URLError("timed out"))
    assert "ValueError" in explain_error(ValueError("x"))


def test_check_ollama(monkeypatch):
    class R:
        def __init__(self, names): self.b = json.dumps({"models": [{"name": n} for n in names]}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, *a): return self.b

    monkeypatch.setattr(brain.urllib.request, "urlopen", lambda *a, **k: R([brain.C.MODEL]))
    assert brain.check_ollama() is None
    monkeypatch.setattr(brain.urllib.request, "urlopen", lambda *a, **k: R(["other:1b"]))
    assert "ollama pull" in brain.check_ollama()

    def boom(*a, **k): raise urllib.error.URLError(ConnectionRefusedError())
    monkeypatch.setattr(brain.urllib.request, "urlopen", boom)
    assert "isn't running" in brain.check_ollama()
