import os
import subprocess
from unittest.mock import patch

from marmot import optimizer
from marmot.optimizer import SystemOptimizer, read_swaps

SWAPS = """Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority
/dev/zram0                              partition\t14180348\t524288\t\t100
/swap\\040file                           file\t\t2097148\t\t0\t\t-2
"""


def test_tasks_listed():
    ids = [t['id'] for t in SystemOptimizer().get_optimizations()]
    assert ids == ["trim", "swap", "dns", "failed", "drop_caches"]


def test_read_swaps():
    assert read_swaps(SWAPS) == [{'name': "/dev/zram0", 'used_kb': 524288, 'prio': 100},
                                 {'name': "/swap file", 'used_kb': 0, 'prio': -2}]


def test_swap_not_offered_when_empty_or_unsafe():
    o = SystemOptimizer()
    with patch.object(optimizer, "read_swaps", return_value=[{'name': "/dev/zram0", 'used_kb': 0, 'prio': 100}]):
        assert not o.check("swap")['applicable']
    with patch.object(optimizer, "read_swaps", return_value=[{'name': "/dev/zram0", 'used_kb': 4_000_000, 'prio': 100}]), \
         patch.object(optimizer, "mem_available_kb", return_value=5_000_000):
        st = o.check("swap")
        assert not st['applicable'] and "not safe" in st['status']


def test_swap_command_cycles_only_used_devices():
    with patch.object(optimizer, "read_swaps", return_value=read_swaps(SWAPS)):
        cmd = SystemOptimizer().command("swap")
    assert cmd[:3] == ["sh", "-c", optimizer._SWAP_CYCLE] and cmd[4:] == ["/dev/zram0", "100"]


def test_swap_script_restores_priority(tmp_path):
    """Run the real shell script with stub swapoff/swapon: zram must come back with its priority."""
    log = tmp_path / "log"
    for tool in ("swapoff", "swapon"):
        stub = tmp_path / tool
        stub.write_text(f'#!/bin/sh\necho "{tool} $*" >> "{log}"\n')
        stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    subprocess.run(["sh", "-c", optimizer._SWAP_CYCLE, "sh", "/dev/zram0", "100", "/swap file", "-2"],
                   check=True, env=env)
    assert log.read_text().splitlines() == [
        "swapoff /dev/zram0", "swapon -p 100 /dev/zram0", "swapoff /swap file", "swapon /swap file"]


def test_swap_script_stops_on_failure(tmp_path):
    for tool, code in (("swapoff", 1), ("swapon", 0)):
        stub = tmp_path / tool
        stub.write_text(f"#!/bin/sh\nexit {code}\n")
        stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    assert subprocess.run(["sh", "-c", optimizer._SWAP_CYCLE, "sh", "/dev/zram0", "100"], env=env).returncode != 0


def test_dns_backends():
    o = SystemOptimizer()
    with patch.object(optimizer, "_out", side_effect=lambda cmd: (0, "") if "systemd-resolved" in cmd else (3, "")):
        assert o.command("dns") == ["resolvectl", "flush-caches"]
    with patch.object(optimizer, "_out", return_value=(3, "")):
        st = o.check("dns")
        assert not st['applicable'] and "nothing to flush" in st['status']


def test_failed_units():
    out = "foo.service loaded failed failed Foo\nbar.mount loaded failed failed Bar\n"
    with patch.object(optimizer, "_out", return_value=(0, out)):
        assert SystemOptimizer().check("failed") == {'applicable': True, 'status': "2 failed: foo.service, bar.mount"}
    with patch.object(optimizer, "_out", return_value=(0, "")):
        assert not SystemOptimizer().check("failed")['applicable']


def test_run_skips_with_reason_and_never_calls_root():
    o = SystemOptimizer()
    with patch.object(optimizer, "_out", return_value=(0, "")), patch.object(optimizer, "run_root") as root:
        ok, msg = o.run_optimization("failed")
    assert not ok and msg.startswith("Skipped") and not root.called


def test_run_and_dry_run():
    o = SystemOptimizer()
    with patch.object(optimizer, "run_root", return_value=(True, "", "/: 1 GiB trimmed")) as root, \
         patch("shutil.which", return_value="/usr/bin/fstrim"), patch.object(optimizer, "_out", return_value=(0, "")):
        ok, msg = o.run_optimization("trim", dry_run=True)
        assert ok and msg == "Would run as root: fstrim -av" and not root.called
        ok, msg = o.run_optimization("trim")
        assert ok and "1 GiB trimmed" in msg
        root.assert_called_once_with(["fstrim", "-av"])


def test_run_failure_message():
    with patch.object(optimizer, "run_root", return_value=(False, "", "Not authorized")):
        ok, msg = SystemOptimizer().run_optimization("drop_caches")
    assert not ok and "Not authorized" in msg


def test_real_checks_do_not_crash():
    o = SystemOptimizer()
    for t in o.get_optimizations():
        st = o.check(t['id'])
        assert isinstance(st['applicable'], bool) and st['status']


