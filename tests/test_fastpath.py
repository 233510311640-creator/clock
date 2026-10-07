from clock import fastpath


def run(text, monkeypatch, calls):
    monkeypatch.setattr(fastpath, "run_tool", lambda n, a, s, c: (calls.append((n, a)) or {"open_app": "Opened notepad."}.get(n, "ok")))
    monkeypatch.setattr(fastpath.audit, "record", lambda *a, **k: None)
    return fastpath.try_fast(text, None, None)


def test_open_app(monkeypatch):
    calls = []
    assert run("Hey Clock, can you open notepad please?", monkeypatch, calls) == "Opening notepad."
    assert calls == [("open_app", {"name": "notepad"})]


def test_volume_set_and_up(monkeypatch):
    calls = []
    run("Set volume to 30 percent.", monkeypatch, calls)
    run("Turn it up", monkeypatch, calls)
    assert calls == [("volume", {"action": "set", "level": 30}), ("volume", {"action": "up"})]


def test_timer(monkeypatch):
    calls = []
    assert run("Set a timer for 5 minutes", monkeypatch, calls) == "Timer set for 5 minutes."
    assert calls == [("set_timer", {"seconds": 300})]


def test_time_and_date_need_no_tool(monkeypatch):
    calls = []
    assert "It's" in run("What time is it?", monkeypatch, calls)
    assert "It's" in run("What's the date today?", monkeypatch, calls)
    assert calls == []


def test_complex_requests_fall_through(monkeypatch):
    calls = []
    for text in ("Open the pod bay doors and tell me a joke", "Open my resume and summarise it",
                 "What time does the shop close?", "Set the volume to something nice", "play me some jazz"):
        assert run(text, monkeypatch, calls) is None
    assert calls == []
