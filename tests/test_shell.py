import pytest

from clock import audit, shell

YES, NO = (lambda q: True), (lambda q: False)


@pytest.mark.parametrize("cmd", [
    "Get-Process", "get-date", "hostname", "whoami", "ipconfig /all", "systeminfo", "python --version",
    "Get-Process | Sort-Object CPU | Select-Object -First 5", "pip list", "tasklist",
])
def test_look_only_commands_run_without_asking(cmd):
    assert shell.is_safe(cmd)


@pytest.mark.parametrize("cmd", [
    "Remove-Item x.txt", "Get-Process; Remove-Item x", "Get-Process && calc", "Get-Process > out.txt",
    "Get-Process | Out-File x.txt", "Get-Content C:/secret.txt", "Get-Date $(calc)", "Get-Date `n calc",
    "python script.py", "git push", "echo hi", "Get-Process | Stop-Process", "Get-Process\ncalc", "",
])
def test_everything_else_needs_a_yes(cmd):
    assert not shell.is_safe(cmd)


def test_unsafe_command_is_declined_without_running(tmp_path, monkeypatch):
    monkeypatch.setattr(shell.C, "ALLOWED_DIR", tmp_path)
    assert shell.run("New-Item made.txt", NO) == "User declined."
    assert not (tmp_path / "made.txt").exists()
    assert shell.run("New-Item made.txt", YES).startswith("Finished (exit 0)")
    assert (tmp_path / "made.txt").exists()


def test_safe_command_runs_and_returns_output(tmp_path, monkeypatch):
    monkeypatch.setattr(shell.C, "ALLOWED_DIR", tmp_path)
    asked = []
    out = shell.run("Get-Date -Format yyyy", lambda q: asked.append(q) or False)
    assert not asked and out.startswith("Finished (exit 0).") and "20" in out


def test_never_list_and_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(shell.C, "ALLOWED_DIR", tmp_path)
    assert "won't run" in shell.run("Format-Volume -DriveLetter D", YES)
    assert "won't run" in shell.run("diskpart", YES)
    monkeypatch.setattr(shell, "TIMEOUT", 1)
    assert "longer than 1 seconds" in shell.run("Start-Sleep 5", YES)


def test_audit_risk_for_commands():
    assert audit.risk("run_command", {"command": "Get-Process"}) == "read"
    assert audit.risk("run_command", {"command": "Remove-Item x"}) == "write"
