"""File actions inside the approved folders (ALLOWED_DIR plus CLOCK_DIRS). Nothing outside them is read or changed.

Overwriting and deleting always ask first; delete sends the file to the Recycle Bin, so it can be restored.
"""
import ctypes
import os
import shutil
from ctypes import wintypes
from pathlib import Path

from . import config as C

MAX_READ = 4000
LIST_LIMIT = 60
# A file Windows can run on its own: planting one is how a prompt-injected "save this" becomes code execution.
RISKY_EXT = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".jse", ".wsf", ".lnk", ".scr", ".msi", ".reg", ".dll", ".hta"}
OUTSIDE = "That path is outside the approved folders."


def roots():
    return [C.ALLOWED_DIR] + [d for d in C.EXTRA_DIRS if d != C.ALLOWED_DIR]


def resolve(p: str):
    """A path as the user said it -> a real Path inside an approved folder, else None.
    Relative paths start in ALLOWED_DIR, unless the first part names another approved folder ("Desktop/notes.txt")."""
    p = (p or "").strip().strip('"')
    if not p:
        return None
    raw = Path(p)
    if raw.is_absolute():
        cand = raw
    else:
        base = next((r for r in roots() if raw.parts and raw.parts[0].lower() == r.name.lower()), None)
        cand = (base.parent / raw) if base else (C.ALLOWED_DIR / raw)
    try:
        cand = cand.resolve()  # follows links, so a shortcut out of the folder does not count as inside
    except (OSError, RuntimeError):
        return None
    return cand if any(cand == r or cand.is_relative_to(r) for r in roots()) else None


def list_folder(path: str = "") -> str:
    if not path.strip():
        return "Approved folders:\n" + "\n".join(str(r) for r in roots())
    p = resolve(path)
    if not p:
        return OUTSIDE
    if not p.is_dir():
        return "That folder doesn't exist."
    rows = []
    for e in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))[:LIST_LIMIT]:
        rows.append(f"{e.name}/" if e.is_dir() else f"{e.name} ({e.stat().st_size} bytes)")
    return "\n".join(rows) or "Empty folder."


def search(query: str) -> str:
    q, hits = query.lower(), []
    for root in roots():
        for dirpath, _, names in os.walk(root):
            hits += [os.path.join(dirpath, n) for n in names if q in n.lower()]
            if len(hits) >= 10:
                return "\n".join(hits[:10])
    return "\n".join(hits) or "No matches."


MAX_PDF_PAGES = 200


def _extract(p: Path) -> str:
    """The text of a file: plain text, Word (.docx, tables included) or PDF. Raises ValueError with a spoken reason."""
    ext = p.suffix.lower()
    if ext == ".docx":
        import docx
        try:
            doc = docx.Document(str(p))
        except Exception as e:
            raise ValueError(f"I couldn't open that Word file ({type(e).__name__}).") from e
        lines = [para.text for para in doc.paragraphs]
        for table in doc.tables:
            lines += [" | ".join(c.text.strip() for c in row.cells) for row in table.rows]
        return "\n".join(line for line in lines if line.strip())
    if ext == ".pdf":
        import pypdf
        try:
            reader = pypdf.PdfReader(str(p))
            if reader.is_encrypted:
                raise ValueError("That PDF is password-protected.")
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PDF_PAGES])
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"I couldn't open that PDF ({type(e).__name__}).") from e
        if not text.strip():
            raise ValueError("That PDF has no text I can read; it may be a scan.")
        return text
    return p.read_text(encoding="utf-8", errors="replace")


def read(path: str, offset: int = 0) -> str:
    """One window of MAX_READ characters. Long files say where to continue."""
    p = resolve(path)
    if not p or not p.is_file():
        return "File not found or outside the approved folders."
    try:
        text = _extract(p)
    except ValueError as e:
        return str(e)
    offset = max(0, offset)
    chunk = text[offset:offset + MAX_READ]
    if not chunk:
        return "Nothing there: that is past the end of the file."
    more = offset + MAX_READ
    return chunk + (f"\n...(more: call read_file again with offset {more} of {len(text)})" if more < len(text) else "")


def write(path: str, text: str, mode: str, confirm) -> str:
    p = resolve(path)
    if not p:
        return OUTSIDE
    if p.is_dir():
        return "That is a folder."
    if p.suffix.lower() in RISKY_EXT and not confirm(f"{p.name} is a program or script file. Create it anyway?"):
        return "User declined."
    if mode == "create" and p.exists():
        return f"{p.name} already exists. Use append, or overwrite if you mean to replace it."
    if mode == "overwrite" and p.exists() and not confirm(f"Overwrite {p.name}?"):
        return "User declined."
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a" if mode == "append" else "w", encoding="utf-8") as f:
        f.write(text)
    return f"Wrote {p.name}."


def make_folder(path: str) -> str:
    p = resolve(path)
    if not p:
        return OUTSIDE
    p.mkdir(parents=True, exist_ok=True)
    return f"Folder ready: {p.name}."


def _transfer(src: str, dst: str, confirm, move: bool) -> str:
    s, d = resolve(src), resolve(dst)
    if not s or not d:
        return OUTSIDE
    if not s.exists():
        return "Source not found."
    if not move and not s.is_file():
        return "Only single files can be copied."
    if d.is_dir():
        d = d / s.name
    if d == s:
        return "Source and destination are the same."
    if d.exists() and not confirm(f"{d.name} already exists. Replace it?"):
        return "User declined."
    d.parent.mkdir(parents=True, exist_ok=True)
    (shutil.move if move else shutil.copy2)(str(s), str(d))
    return f"{'Moved' if move else 'Copied'} {s.name}."


def move(src: str, dst: str, confirm) -> str:
    return _transfer(src, dst, confirm, True)


def copy(src: str, dst: str, confirm) -> str:
    return _transfer(src, dst, confirm, False)


class _FileOp(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("func", wintypes.UINT), ("src", wintypes.LPCWSTR), ("dst", wintypes.LPCWSTR),
                ("flags", ctypes.c_ushort), ("aborted", wintypes.BOOL), ("mappings", ctypes.c_void_p),
                ("title", wintypes.LPCWSTR)]


def _recycle(p: Path) -> bool:
    """Send a file to the Recycle Bin (FO_DELETE + FOF_ALLOWUNDO), no Windows dialog."""
    op = _FileOp(None, 3, str(p) + "\0", None, 0x40 | 0x10 | 0x4 | 0x400, False, None, None)  # undo, no prompt, silent, no error UI
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.aborted


def delete(path: str, confirm) -> str:
    p = resolve(path)
    if not p:
        return OUTSIDE
    if p in roots():
        return "I won't delete an approved folder itself."
    if not p.is_file():
        return "File not found. I only delete single files."
    if not confirm(f"Delete {p.name}? It goes to the Recycle Bin."):
        return "User declined."
    return f"Moved {p.name} to the Recycle Bin." if _recycle(p) else f"Couldn't delete {p.name}."
