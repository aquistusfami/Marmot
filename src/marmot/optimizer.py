"""Maintenance tasks. Each task first checks whether it applies on this machine (and says why not),
so the UI never offers a button that does nothing or something harmful."""
import shutil
import subprocess

from marmot.privilege import run_root

# swapoff + swapon one device at a time, restoring its priority; devices/priorities are argv, never spliced
_SWAP_CYCLE = ('set -e; while [ $# -gt 1 ]; do swapoff "$1"; '
               'if [ "$2" -ge 0 ] 2>/dev/null; then swapon -p "$2" "$1"; else swapon "$1"; fi; shift 2; done')

TASKS = [
    {'id': 'trim', 'name': "Trim SSDs",
     'desc': "Tells SSDs which blocks are free (fstrim -av), keeping write speed up. Safe on every filesystem that supports it."},
    {'id': 'swap', 'name': "Reclaim swap",
     'desc': "Moves swapped-out pages back into RAM, one swap device at a time, and re-enables each with the same priority "
             "(zram included). Only offered when RAM can hold it."},
    {'id': 'dns', 'name': "Flush DNS cache",
     'desc': "Clears the local resolver cache (systemd-resolved or nscd), e.g. after changing DNS servers or /etc/hosts."},
    {'id': 'failed', 'name': "Clear failed services",
     'desc': "Clears systemd's failed state so the list starts fresh. This does not fix the services: read their logs first."},
    {'id': 'drop_caches', 'name': "Drop page cache",
     'desc': "For benchmarking only. The kernel already frees this cache on demand, so dropping it makes the system "
             "slower until the cache refills."},
]


def _fmt(kb: int) -> str:
    return f"{kb / 1024**2:.1f} GB" if kb >= 1024**2 else f"{kb / 1024:.0f} MB"


def _out(cmd: list) -> tuple[int, str]:
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=15)
        return res.returncode, res.stdout.decode(errors="ignore")
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def read_swaps(text: str | None = None) -> list:
    """/proc/swaps -> [{name, used_kb, prio}] (paths with spaces are \\040-escaped by the kernel)."""
    if text is None:
        try:
            with open("/proc/swaps") as f:
                text = f.read()
        except OSError:
            return []
    swaps = []
    for line in text.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 5:
            swaps.append({'name': cols[0].replace("\\040", " "), 'used_kb': int(cols[3]), 'prio': int(cols[4])})
    return swaps


def mem_available_kb() -> int:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


class SystemOptimizer:
    def get_optimizations(self) -> list:
        return [dict(t) for t in TASKS]

    # ---- checks: {'applicable': bool, 'status': str} -----------------------

    def check(self, task_id: str) -> dict:
        return getattr(self, f"_check_{task_id}")()

    def _check_trim(self) -> dict:
        if not shutil.which("fstrim"):
            return {'applicable': False, 'status': "fstrim is not installed (util-linux)."}
        rc, _ = _out(["systemctl", "is-enabled", "fstrim.timer"])
        timer = "weekly fstrim.timer is enabled, so this is rarely needed" if rc == 0 else "fstrim.timer is not enabled"
        return {'applicable': True, 'status': timer.capitalize() + "."}

    def _check_swap(self) -> dict:
        swaps = read_swaps()
        if not swaps:
            return {'applicable': False, 'status': "No swap is configured."}
        used = sum(s['used_kb'] for s in swaps)
        if used == 0:
            return {'applicable': False, 'status': f"Nothing in swap ({', '.join(s['name'] for s in swaps)})."}
        avail = mem_available_kb()
        if avail < used * 1.5:  # margin so pulling pages back cannot push the system into OOM
            return {'applicable': False,
                    'status': f"{_fmt(used)} in swap but only {_fmt(avail)} RAM available: not safe."}
        return {'applicable': True, 'status': f"{_fmt(used)} in swap, {_fmt(avail)} RAM available."}

    def _dns_backend(self) -> list | None:
        if _out(["systemctl", "is-active", "--quiet", "systemd-resolved"])[0] == 0:
            return ["resolvectl", "flush-caches"]
        if _out(["systemctl", "is-active", "--quiet", "nscd"])[0] == 0:
            return ["nscd", "--invalidate=hosts"]
        return None

    def _check_dns(self) -> dict:
        cmd = self._dns_backend()
        if cmd is None:
            return {'applicable': False,
                    'status': "No local DNS cache running (systemd-resolved/nscd): nothing to flush."}
        return {'applicable': True, 'status': f"Uses {cmd[0]}."}

    def failed_units(self) -> list:
        _, out = _out(["systemctl", "--failed", "--no-legend", "--plain"])
        return [ln.split()[0] for ln in out.splitlines() if ln.strip()]

    def _check_failed(self) -> dict:
        units = self.failed_units()
        if not units:
            return {'applicable': False, 'status': "No failed services."}
        return {'applicable': True, 'status': f"{len(units)} failed: {', '.join(units[:5])}"
                                              f"{'...' if len(units) > 5 else ''}"}

    def _check_drop_caches(self) -> dict:
        return {'applicable': True, 'status': "Not recommended for normal use."}

    # ---- run -------------------------------------------------------------------

    def command(self, task_id: str) -> list | None:
        """The root command a task would run (None if not applicable now)."""
        if task_id == 'trim':
            return ["fstrim", "-av"]
        if task_id == 'swap':
            argv = [x for s in read_swaps() if s['used_kb'] > 0 for x in (s['name'], str(s['prio']))]
            return ["sh", "-c", _SWAP_CYCLE, "sh", *argv] if argv else None
        if task_id == 'dns':
            return self._dns_backend()
        if task_id == 'failed':
            return ["systemctl", "reset-failed"]
        if task_id == 'drop_caches':
            return ["sh", "-c", "sync && echo 3 > /proc/sys/vm/drop_caches"]
        raise KeyError(task_id)

    def run_optimization(self, task_id: str, dry_run: bool = False) -> tuple[bool, str]:
        state = self.check(task_id)
        if not state['applicable']:
            return False, f"Skipped: {state['status']}"
        cmd = self.command(task_id)
        if cmd is None:
            return False, "Skipped: nothing to do."
        if dry_run:
            shown = cmd[:2] + ["…"] if cmd[0] == "sh" else cmd
            return True, f"Would run as root: {' '.join(shown)}"
        ok, via, out = run_root(cmd)
        name = next(t['name'] for t in TASKS if t['id'] == task_id)
        if not ok:
            return False, f"{name} failed: {out}"
        return True, f"{name} done{via}" + (f": {out}" if out else "")
