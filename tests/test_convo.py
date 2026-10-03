from clock import convo


def test_inbox_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(convo, "INBOX_FILE", tmp_path / "inbox")
    assert convo.take() == []
    convo.send("what time is it")
    convo.send("  multi\nline  ")
    assert convo.take() == ["what time is it", "multi line"]
    assert convo.take() == []


def test_transcript(tmp_path, monkeypatch):
    monkeypatch.setattr(convo, "CONVO_FILE", tmp_path / "convo.jsonl")
    convo.add("you", "hi")
    convo.add("clock", "  ")  # blank is ignored
    convo.add("clock", "hello")
    assert [m["who"] for m in convo.read()] == ["you", "clock"]


def test_settings(tmp_path, monkeypatch):
    from clock import settings
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "s.json")
    assert settings.load() == settings.defaults()
    settings.save({"voice": False, "bogus": True})
    cfg = settings.load()
    assert cfg["voice"] is False and cfg["chime"] == settings.defaults()["chime"] and "bogus" not in cfg
