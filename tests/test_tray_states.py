import pytest

from clock import settings
from clock.launcher import icon_state


@pytest.mark.parametrize("running, detail, want", [
    (False, "", "off"),
    (False, "listening", "off"),
    (True, "", "waiting"),
    (True, "loading", "waiting"),
    (True, "listening", "waiting"),
    (True, "hearing you", "active"),
    (True, "thinking", "active"),
    (True, "speaking", "active"),
    (True, "waiting for your request", "active"),
    (True, "muted", "muted"),
    (True, "mic silent - muted?", "nomic"),
    (True, "mic unavailable", "nomic"),
])
def test_icon_state(running, detail, want):
    assert icon_state(running, detail) == want


def test_listening_setting_defaults_on_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "s.json")
    assert settings.load()["listening"] is True
    settings.save({"listening": False})
    assert settings.load()["listening"] is False
    settings.save({"hud": True})  # saving another key keeps the mute
    assert settings.load()["listening"] is False


def test_every_tray_icon_exists():
    from clock.launcher import HERE
    for name in ("off", "waiting", "active", "muted", "nomic"):
        assert (HERE / "assets" / f"tray_{name}.png").exists()
