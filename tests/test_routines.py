import datetime

import pytest

from clock import config as C
from clock import reminders, routines, tools


@pytest.fixture(autouse=True)
def tmp_routines(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROUTINES_FILE", tmp_path / "routines.json")


def at(day, hhmm):
    """Datetime on Monday 2026-10-05 + day offset."""
    base = datetime.datetime(2026, 10, 5) + datetime.timedelta(days=day)
    h, m = map(int, hhmm.split(":"))
    return base.replace(hour=h, minute=m)


def test_parse_days():
    assert routines.parse_days("weekdays") == [0, 1, 2, 3, 4]
    assert routines.parse_days("weekends") == [5, 6]
    assert routines.parse_days("daily") == list(range(7))
    assert routines.parse_days("Mon, wednesday,FRI") == [0, 2, 4]
    with pytest.raises(ValueError):
        routines.parse_days("funday")


def test_parse_time():
    assert routines.parse_time("8:30") == "08:30"
    assert routines.parse_time("17") == "17:00"
    for bad in ("25:00", "8:75", "soon"):
        with pytest.raises(ValueError):
            routines.parse_time(bad)


def test_add_list_cancel():
    assert "8:00 AM on weekdays" in routines.add("08:00", "weekdays", "weather,reminders")
    assert "weather, reminders" in routines.listing()
    assert routines.cancel("weather").startswith("Cancelled 1")
    assert routines.listing() == "No routines."
    assert routines.cancel("nothing") == "No matching routine."


def test_add_rejects_empty_and_bad_part():
    assert "needs something to say" in routines.add("08:00")
    with pytest.raises(ValueError):
        routines.add("08:00", "daily", "stocks")


def test_limit():
    for _ in range(routines.MAX_ROUTINES):
        routines.add("08:00", text="hi")
    assert "Too many" in routines.add("09:00", text="hi")


def test_runs_once_per_day_on_listed_days_only():
    routines.add("08:00", "weekdays", text="Good morning")
    assert routines.pop_due(at(0, "07:59")) == []                    # not yet
    due = routines.pop_due(at(0, "08:00"))
    assert len(due) == 1 and due[0][1] is False                      # on time
    assert routines.pop_due(at(0, "08:05")) == []                    # already ran today
    assert routines.pop_due(at(5, "08:00")) == []                    # Saturday: not a listed day
    assert len(routines.pop_due(at(1, "08:00"))) == 1                # next day runs again


def test_late_but_recent_is_spoken_and_flagged():
    routines.add("08:00", "daily", text="hi")
    (item, late), = routines.pop_due(at(0, "09:30"))  # 90 min late
    assert late is True and item["text"] == "hi"


def test_stale_routine_is_skipped_not_deferred():
    routines.add("06:00", "daily", text="early")
    assert routines.pop_due(at(0, "10:00")) == []
    assert routines.pop_due(at(0, "10:01")) == []                    # marked as run, not retried


def test_compose_parts(monkeypatch):
    from clock import web
    monkeypatch.setattr(web, "weather", lambda city="": "Delhi: 30C.")
    monkeypatch.setattr(reminders, "pending", lambda: [{"id": "a", "due": at(0, "17:00").isoformat(), "text": "call mum", "kind": "reminder"}])
    item = {"text": "Good morning", "parts": ["time", "weather", "reminders"]}
    msg = routines.compose(item, now=at(0, "08:00"))
    assert msg.startswith("Good morning It is 8:00 AM on Monday.")
    assert "Delhi: 30C." in msg and "call mum at 5:00 PM" in msg


def test_compose_survives_failed_part(monkeypatch):
    from clock import web

    def boom(city=""):
        raise OSError("offline")
    monkeypatch.setattr(web, "weather", boom)
    msg = routines.compose({"text": "Hi", "parts": ["weather", "time"]}, now=at(0, "08:00"))
    assert "Hi" in msg and "It is 8:00 AM" in msg


def test_tool_reports_bad_input():
    assert tools.run_tool("add_routine", {"at": "99:00", "text": "x"}, None, None).startswith("Couldn't set that routine")
    assert "Routine set" in tools.run_tool("add_routine", {"at": "08:00", "include": "time"}, None, None)
