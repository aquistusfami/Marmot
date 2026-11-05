"""Undoable deletion: freedesktop.org Trash + an action history for `marmot undo`.

Trashed items show up in every file manager's Trash and can be restored there too.
"""
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import quote, unquote


def trash_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "Trash"


def history_file() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "marmot" / "history.jsonl"


def move_to_trash(path: str | Path) -> str:
    """Move `path` into the user Trash (spec-compliant .trashinfo). Returns the name inside Trash/files."""
    src = Path(path).absolute()
    if not src.exists() and not src.is_symlink():
        raise FileNotFoundError(src)
    files, info = trash_dir() / "files", trash_dir() / "info"
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)

    base, n = src.name, 1
    while True:
        name = base if n == 1 else f"{base}.{n}"
        try:
            # O_EXCL reserves the name atomically, as the spec requires
            fd = os.open(info / f"{name}.trashinfo", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            n += 1
            continue
        if (files / name).exists():
            os.close(fd)
            os.unlink(info / f"{name}.trashinfo")
            n += 1
            continue
        break
    with os.fdopen(fd, "w") as f:
        f.write(f"[Trash Info]\nPath={quote(str(src))}\nDeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
    try:
        # shortcut: files on another filesystem are copied into the home Trash instead of $topdir/.Trash-$uid;
        # fine for Marmot's targets (all under $HOME), revisit if it ever trashes other mounts.
        shutil.move(str(src), str(files / name))
    except BaseException:
        os.unlink(info / f"{name}.trashinfo")
        raise
    return name


def restore_from_trash(name: str) -> Path:
    """Move a trashed entry back to its original path. Refuses to overwrite."""
    info = trash_dir() / "info" / f"{name}.trashinfo"
    original = None
    for line in info.read_text().splitlines():
        if line.startswith("Path="):
            original = Path(unquote(line[5:]))
    if original is None:
        raise ValueError(f"{info} has no Path=")
    if original.exists() or original.is_symlink():
        raise FileExistsError(f"{original} already exists, not overwriting")
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trash_dir() / "files" / name), str(original))
    info.unlink()
    return original


# ---- history -------------------------------------------------------------

def record(action: str, *, freed: int = 0, trashed: list | None = None, detail: str = "",
           undoes: str | None = None) -> dict:
    """Append one action. `trashed` = [{"name": <Trash/files name>, "path": <original>}]."""
    entry = {"id": uuid.uuid4().hex[:12], "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "action": action,
             "freed": freed, "trashed": trashed or [], "detail": detail, "undoes": undoes}
    hf = history_file()
    hf.parent.mkdir(parents=True, exist_ok=True)
    with hf.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def load_history() -> list:
    try:
        lines = history_file().read_text().splitlines()
    except FileNotFoundError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass  # a torn line from a crash must not hide the rest
    return out


def last_undoable() -> dict | None:
    hist = load_history()
    undone = {e.get("undoes") for e in hist}
    return next((e for e in reversed(hist) if e["trashed"] and e["id"] not in undone), None)


def undo_last() -> tuple[dict | None, list, list]:
    """Restore everything the last undoable action trashed. Returns (entry, restored, errors)."""
    entry = last_undoable()
    if entry is None:
        return None, [], []
    restored, errors = [], []
    for t in entry["trashed"]:
        try:
            restored.append(str(restore_from_trash(t["name"])))
        except (OSError, ValueError) as e:
            errors.append(f"{t['path']}: {e}")
    record("undo", detail=f"undo {entry['action']}", undoes=entry["id"])
    return entry, restored, errors
