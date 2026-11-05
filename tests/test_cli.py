import json
from unittest.mock import MagicMock, patch

from marmot import cli

FAKE = {'trash': {'name': "System Trash", 'size': 10, 'size_str': "10 B", 'requires_sudo': False, 'desc': ""}}


def _cleaner(ok=True):
    c = MagicMock()
    c.scan.return_value = FAKE
    c.clean.return_value = (ok, "Would permanently delete 10 B")
    return c


def test_scan_json(capsys):
    with patch('marmot.cli._scan', return_value=(_cleaner(), FAKE)):
        assert cli.main(["scan", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)['trash']['size'] == 10


def test_clean_unknown_item_is_usage_error(capsys):
    with patch('marmot.cli._scan', return_value=(_cleaner(), FAKE)):
        assert cli.main(["clean", "nope"]) == 2
    assert "Available: trash" in capsys.readouterr().err


def test_clean_refuses_non_interactive_without_yes():
    c = _cleaner()
    with patch('marmot.cli._scan', return_value=(c, FAKE)), patch('sys.stdin.isatty', return_value=False):
        assert cli.main(["clean", "trash"]) == 2
    c.clean.assert_not_called()


def test_clean_dry_run_passes_flag():
    c = _cleaner()
    with patch('marmot.cli._scan', return_value=(c, FAKE)):
        assert cli.main(["clean", "trash", "--dry-run"]) == 0
    assert c.clean.call_args.kwargs['dry_run'] is True


def test_clean_failure_exit_code():
    with patch('marmot.cli._scan', return_value=(_cleaner(ok=False), FAKE)):
        assert cli.main(["clean", "trash", "--yes"]) == 1


def test_status_json(capsys):
    assert cli.main(["status", "--json"]) == 0
    assert "memory" in json.loads(capsys.readouterr().out)


def test_undo_nothing():
    assert cli.main(["undo"]) == 1
