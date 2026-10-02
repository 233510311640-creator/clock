import pytest

from edith import config as C


@pytest.fixture(autouse=True)
def isolated_files(tmp_path, monkeypatch):
    """Never touch the real memory/reminder/notes files."""
    monkeypatch.setattr(C, "MEMORY_FILE", tmp_path / "memory.json")
    monkeypatch.setattr(C, "REMINDERS_FILE", tmp_path / "reminders.json")
    monkeypatch.setattr(C, "NOTES_FILE", tmp_path / "notes.txt")
