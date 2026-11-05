from pathlib import Path

import pytest

from marmot import trash


def test_trash_and_restore_roundtrip(tmp_path):
    victim = tmp_path / "proj" / "node_modules"
    victim.mkdir(parents=True)
    (victim / "x.js").write_text("hi")

    name = trash.move_to_trash(victim)
    assert not victim.exists()
    info = (trash.trash_dir() / "info" / f"{name}.trashinfo").read_text()
    assert f"Path={victim}" in info and "DeletionDate=" in info

    assert trash.restore_from_trash(name) == victim
    assert (victim / "x.js").read_text() == "hi"
    assert not (trash.trash_dir() / "info" / f"{name}.trashinfo").exists()


def test_name_collisions_get_suffix(tmp_path):
    names = []
    for i in range(3):
        d = tmp_path / str(i) / ".venv"
        d.mkdir(parents=True)
        names.append(trash.move_to_trash(d))
    assert names == [".venv", ".venv.2", ".venv.3"]


def test_restore_never_overwrites(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("old")
    name = trash.move_to_trash(f)
    f.write_text("new")
    with pytest.raises(FileExistsError):
        trash.restore_from_trash(name)
    assert f.read_text() == "new"


def test_undo_last_restores_batch_once(tmp_path):
    paths = [tmp_path / "a", tmp_path / "b"]
    for p in paths:
        p.mkdir()
    trashed = [{"name": trash.move_to_trash(p), "path": str(p)} for p in paths]
    trash.record("clean:dev_junk", trashed=trashed)
    trash.record("clean:trash", freed=10)  # not undoable, must be skipped

    entry, restored, errors = trash.undo_last()
    assert entry["action"] == "clean:dev_junk" and not errors
    assert sorted(restored) == sorted(map(str, paths)) and all(p.exists() for p in paths)
    assert trash.undo_last() == (None, [], [])  # already undone


def test_history_survives_torn_line():
    trash.record("a")
    with trash.history_file().open("a") as f:
        f.write('{"broken": \n')
    trash.record("b")
    assert [e["action"] for e in trash.load_history()] == ["a", "b"]


def test_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        trash.move_to_trash(tmp_path / "nope")
    assert not list((trash.trash_dir() / "info").glob("*")) if (trash.trash_dir() / "info").exists() else True


def test_trash_dir_follows_xdg(tmp_path):
    assert trash.trash_dir() == Path(tmp_path / "data" / "Trash")
