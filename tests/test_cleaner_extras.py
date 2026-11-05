from pathlib import Path
from unittest.mock import MagicMock, patch

from marmot import trash
from marmot.cleaner import SystemCleaner, parse_disabled_snaps, parse_size


def test_parse_size():
    assert parse_size("120.4MB") == int(120.4 * 1024**2)
    assert parse_size("1.2G") == int(1.2 * 1024**3)
    assert parse_size("3.5 GiB") == int(3.5 * 1024**3)
    assert parse_size("0B (0%)") == 0
    assert parse_size("n/a") == -1


def test_parse_disabled_snaps():
    out = """Name    Version   Rev    Tracking       Publisher   Notes
core22  20240111  1122   latest/stable  canonical✓  base,disabled
core22  20240408  1380   latest/stable  canonical✓  base
firefox 125.0     4173   latest/stable  mozilla✓    disabled
"""
    assert [(r['name'], r['rev']) for r in parse_disabled_snaps(out)] == [("core22", "1122"), ("firefox", "4173")]


def _home(tmp_path):
    h = tmp_path / "home"
    (h / ".cache" / "big").mkdir(parents=True)
    (h / ".cache" / "big" / "f").write_bytes(b"x" * 500)
    (h / ".cache" / "keep").mkdir()
    (h / ".cache" / "keep" / "f").write_bytes(b"x" * 100)
    return h


def test_user_cache_per_folder_and_dry_run(tmp_path):
    h = _home(tmp_path)
    with patch('pathlib.Path.home', return_value=h), patch('subprocess.check_output', side_effect=OSError):
        c = SystemCleaner(backend="pacman")
        data = c.scan()
    kids = data['user_cache']['children']
    assert [k['name'] for k in kids] == ["big", "keep"] and data['user_cache']['size'] == 600

    ok, msg = c.clean('user_cache', data, dry_run=True, selected=[str(h / ".cache" / "big")])
    assert ok and "Would delete 1" in msg and (h / ".cache" / "big").exists()

    ok, _ = c.clean('user_cache', data, selected=[str(h / ".cache" / "big")])
    assert ok and not (h / ".cache" / "big").exists() and (h / ".cache" / "keep").exists()


def test_user_cache_refuses_paths_outside_cache(tmp_path):
    h = _home(tmp_path)
    precious = tmp_path / "precious"
    precious.mkdir()
    data = {'user_cache': {'path': str(h / ".cache"), 'size': 1,
                           'children': [{'name': "x", 'path': str(precious), 'size': 1}]}}
    with patch('pathlib.Path.home', return_value=h):
        SystemCleaner(backend="pacman").clean('user_cache', data)
    assert precious.exists()


def test_dev_junk_goes_to_trash_and_undo_restores(tmp_path):
    h = tmp_path / "home"
    nm = h / "web" / "node_modules"
    nm.mkdir(parents=True)
    (h / "web" / "package.json").touch()
    with patch('pathlib.Path.home', return_value=h), patch('subprocess.check_output', side_effect=OSError):
        c = SystemCleaner(backend="pacman")
        data = c.scan()
        ok, msg = c.clean('dev_junk', data)
    assert ok and "Trash" in msg and not nm.exists()
    entry, restored, errors = trash.undo_last()
    assert entry['action'] == "clean:dev_junk" and restored == [str(nm)] and nm.exists() and not errors


def test_dry_run_never_runs_commands(tmp_path):
    c = SystemCleaner(backend="apt")
    data = {'pkg_cache': {'size': 1}, 'orphans': {'size': -1, 'packages': ["a"]},
            'systemd_logs': {'size': 1}, 'containers': {'size': 1, 'tool': "podman"},
            'flatpak_unused': {'size': -1}, 'snap_old': {'size': 1, 'revisions': [{'name': "x", 'rev': "1", 'size': 1}]}}
    with patch('subprocess.run') as run:
        for item in data:
            ok, msg = c.clean(item, data, dry_run=True)
            assert ok and msg.startswith("Would"), (item, msg)
        run.assert_not_called()


def test_orphans_and_snap_commands():
    c = SystemCleaner(backend="pacman")
    with patch('subprocess.run', return_value=MagicMock(stdout=b"")) as run:
        c.clean('orphans', {'orphans': {'size': -1, 'packages': ["a", "b"]}})
        assert run.call_args.args[0] == ["pkexec", "pacman", "-Rns", "--noconfirm", "a", "b"]
        revs = [{'name': "core22", 'rev': "1122", 'size': 0}, {'name': "evil;rm -rf ~", 'rev': "1", 'size': 0}]
        c.clean('snap_old', {'snap_old': {'size': 0, 'revisions': revs}})
        cmd = run.call_args.args[0]
        # names are separate argv entries after the script, never spliced into it
        assert cmd[:3] == ["pkexec", "sh", "-c"] and cmd[-4:] == ["core22", "1122", "evil;rm -rf ~", "1"]


def test_scan_reports_orphans(tmp_path):
    with patch('pathlib.Path.home', return_value=tmp_path), patch('subprocess.check_output', side_effect=OSError), \
         patch('marmot.pkgmgr.query', return_value=["libfoo", "libbar"]):
        data = SystemCleaner(backend="pacman").scan()
    assert data['orphans']['packages'] == ["libfoo", "libbar"] and data['orphans']['size_str'] == "?"


def test_containers_scan_skips_volumes():
    df = b"Images\t1GB (50%)\nContainers\t0B (0%)\nLocal Volumes\t5GB (100%)\nBuild Cache\t512MB\n"
    c = SystemCleaner(backend="pacman")
    with patch('shutil.which', side_effect=lambda t: t == "podman"), \
         patch('subprocess.run', return_value=MagicMock(returncode=0, stdout=df)):
        extras = c._scan_extras()
    assert extras['containers']['tool'] == "podman"
    assert extras['containers']['size'] == 1024**3 + 512 * 1024**2


def test_trash_item_uses_xdg_trash(tmp_path):
    with patch('pathlib.Path.home', return_value=tmp_path), patch('subprocess.check_output', side_effect=OSError):
        data = SystemCleaner(backend="pacman").scan()
    assert Path(data['trash']['path']) == trash.trash_dir()
