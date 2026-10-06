"""Run a PowerShell command for the user. Only a short list of look-only commands runs without a question;
everything else is read back and needs a spoken yes. A few destructive disk commands are never run."""
import re
import subprocess

from . import config as C

TIMEOUT = 30
MAX_OUTPUT = 3000
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

# Commands that only report on the machine and never read your files or change anything.
_SAFE = re.compile(
    r"^(?:get-(?:process|service|date|computerinfo|netipaddress|netadapter|volume|psdrive|timezone|uptime|"
    r"physicaldisk|disk|hotfix|command)|hostname|whoami|systeminfo|ipconfig|tasklist|"
    r"(?:python|git|node|npm|pip|java|ollama)\s+(?:--version|-v|version)|pip\s+list)\b[^;&|<>`$(){}]*$", re.I)
# A pipe is allowed only into a formatting or filtering step, which cannot act on anything.
_PIPE_OK = re.compile(r"^(?:select-object|sort-object|where-object|format-table|format-list|measure-object|"
                      r"out-string|head|select|sort|ft|fl)\b[^;&|<>`$(){}]*$", re.I)
_NEVER = re.compile(r"\b(?:format-volume|format\s+[a-z]:|diskpart|bcdedit|cipher\s+/w|vssadmin\s+delete|clear-disk|"
                    r"remove-partition|initialize-disk)\b", re.I)


def is_safe(command: str) -> bool:
    if re.search(r"[\r\n;&<>`$(){}]|\|\|", command):
        return False
    first, *rest = [part.strip() for part in command.split("|")]
    return bool(_SAFE.match(first)) and all(_PIPE_OK.match(part) for part in rest)


def run(command: str, confirm) -> str:
    command = command.strip()
    if not command:
        return "No command given."
    if _NEVER.search(command):
        return "I won't run that: it can wipe a disk."
    if not is_safe(command) and not confirm(f"Run this command? {command[:140]}"):
        return "User declined."
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                           cwd=C.ALLOWED_DIR, capture_output=True, text=True, timeout=TIMEOUT,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return f"Tool error: the command ran longer than {TIMEOUT} seconds and was stopped."
    out = (r.stdout + r.stderr).strip()
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + "\n...(cut)"
    return f"Finished (exit {r.returncode})." + (f"\n{out}" if out else "")
