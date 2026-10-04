import json
import urllib.error

from clock import brain
from clock.brain import _NEEDS_TOOL, _Sentences, explain_error, trim_history


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


def _call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def _run(monkeypatch, replies, confirm_answer):
    """Drive Brain.ask with scripted model replies; return (tools actually run, confirm prompts)."""
    ran, asked = [], []
    it = iter(replies)
    monkeypatch.setattr(brain, "_chat", lambda *a, **k: next(it))
    monkeypatch.setattr(brain, "run_tool", lambda name, args, *_: ran.append(name) or "ok")
    b = brain.Brain(lambda t: None, lambda q: asked.append(q) or confirm_answer)
    b.ask("tell me about it")
    return ran, asked, b


def test_remember_after_web_read_needs_confirmation(monkeypatch):
    replies = [_call("read_webpage", url="http://x"), _call("remember", fact="evil"), _a("done")]
    ran, asked, b = _run(monkeypatch, replies, confirm_answer=False)
    assert ran == ["read_webpage"] and len(asked) == 1
    assert any(m.get("content") == "User declined." for m in b.history)
    assert any("<untrusted" in (m.get("content") or "") for m in b.history if m["role"] == "tool")


def test_remember_after_web_read_runs_if_confirmed(monkeypatch):
    replies = [_call("read_webpage", url="http://x"), _call("remember", fact="ok"), _a("done")]
    ran, asked, _ = _run(monkeypatch, replies, confirm_answer=True)
    assert ran == ["read_webpage", "remember"] and len(asked) == 1


def test_remember_without_untrusted_read_is_not_prompted(monkeypatch):
    ran, asked, _ = _run(monkeypatch, [_call("remember", fact="x"), _a("done")], confirm_answer=False)
    assert ran == ["remember"] and asked == []


def test_allowed_list_blocks_tools_outside_it(monkeypatch):
    ran = []
    it = iter([_call("remember", fact="x"), _call("web_search", query="q"), _a("done")])
    monkeypatch.setattr(brain, "_chat", lambda *a, **k: next(it))
    monkeypatch.setattr(brain, "run_tool", lambda name, args, *_: ran.append(name) or "ok")
    b = brain.Brain(lambda t: None, lambda q: True, allowed={"web_search"})
    b.ask("find out about it")
    assert ran == ["web_search"]
    assert any(m.get("content") == "That tool is not available here." for m in b.history)


def test_allowed_list_limits_schema_sent_to_model():
    b = brain.Brain(lambda t: None, lambda q: True, allowed={"web_search", "weather"})
    assert {t["function"]["name"] for t in b.tools} == {"web_search", "weather"}
    assert len(brain.Brain(lambda t: None, lambda q: True).tools) == len(brain.OLLAMA_TOOLS)
