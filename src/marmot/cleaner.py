import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from marmot import pkgmgr, trash

# the virtualenv Marmot itself runs from (repo .venv, pipx/uv tool env): never offered as junk
RUNNING_VENV = Path(sys.prefix).resolve()

# build dir -> project files that must sit beside it (None = always junk)
DEV_JUNK_MARKERS = {
    "node_modules": ("package.json",),
    "target": ("Cargo.toml", "pom.xml"),
    ".venv": ("pyproject.toml", "requirements.txt", "setup.py", "uv.lock"),
    "__pycache__": None,
    "build": ("CMakeLists.txt", "meson.build", "setup.py", "pyproject.toml",
              "build.gradle", "build.gradle.kts", "package.json"),
}

UNKNOWN = -1  # size could not be measured (orphans, flatpak runtimes)
_UNITS = {"": 1, "B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}

# remove disabled snap revisions in one pkexec call; names/revisions are passed as argv, never interpolated
_SNAP_REMOVE = 'while [ $# -gt 1 ]; do snap remove "$1" --revision="$2" || exit 1; shift 2; done'


def parse_size(text: str) -> int:
    """'1.2GB', '120.4M', '3.5 GiB', '0B' -> bytes (binary units); UNKNOWN if unparsable."""
    m = re.match(r"\s*([\d.]+)\s*([KMGT]?)i?B?\b", text, re.I)
    return int(float(m[1]) * _UNITS[m[2].upper()]) if m else UNKNOWN


def run_root(cmd: list) -> tuple[bool, str, str]:
    """pkexec first, then passwordless sudo. Returns (ok, " (via sudo)" or "", stdout-or-error)."""
    err = ""
    for prefix, suffix in ((["pkexec"], ""), (["sudo", "-n"], " (via sudo)")):
        try:
            res = subprocess.run([*prefix, *cmd], check=True, capture_output=True)
            return True, suffix, res.stdout.decode("utf-8", errors="ignore").strip()
        except Exception as e:
            err = str(e)
    return False, "", err


class SystemCleaner:
    def __init__(self, backend: str | None = None):
        self.home = Path.home()
        self.pm = pkgmgr.get(backend)
        # backend pinned (tests) -> do not probe the host for extra tools
        self.probe_host = backend is None

    def get_dir_size(self, path: Path) -> int:
        total_size = 0
        try:
            if path.is_file():
                return path.stat().st_size
            for root, _dirs, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        if not os.path.islink(fp):
                            total_size += os.path.getsize(fp)
                    except OSError:
                        pass
        except Exception:
            pass
        return total_size

    def format_size(self, size_bytes: int) -> str:
        if size_bytes == UNKNOWN:
            return "?"
        if size_bytes == 0:
            return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_name) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_name[i]}"

    def _item(self, name: str, path: str, size: int, desc: str, sudo: bool, **extra) -> dict:
        return {'name': name, 'path': path, 'size': size, 'size_str': self.format_size(size),
                'desc': desc, 'requires_sudo': sudo, **extra}

    # ---- scan ----------------------------------------------------------------

    def scan(self) -> dict:
        results = {}

        # 1. User cache, per application folder so the user can keep e.g. a browser cache
        cache_path = self.home / ".cache"
        children = []
        try:
            for entry in cache_path.iterdir():
                if entry.is_symlink():
                    continue
                sz = self.get_dir_size(entry)
                children.append({'name': entry.name, 'path': str(entry), 'size': sz, 'size_str': self.format_size(sz)})
        except OSError:
            pass
        children.sort(key=lambda c: c['size'], reverse=True)
        cache_size = sum(c['size'] for c in children) if children else self.get_dir_size(cache_path)
        results['user_cache'] = self._item(
            "User Caches", str(cache_path), cache_size,
            "Temporary application cache files (Chrome, Firefox, Spotify, etc.)", False, children=children)

        # 2. Trash
        trash_path = trash.trash_dir()
        trash_size = self.get_dir_size(trash_path)
        results['trash'] = self._item("System Trash", str(trash_path), trash_size,
                                      "Files in your trash bin (deleted permanently)", False)

        # 3. Package manager cache
        if self.pm and self.pm['cache_dir'] is not None:
            cache_dir = self.pm['cache_dir']
            size = 0
            try:
                for f in cache_dir.glob(self.pm['cache_glob']):
                    try:
                        size += f.stat().st_size
                    except OSError:
                        pass
            except OSError:
                pass  # missing/unreadable cache dir (Python < 3.13 raises from glob)
            results['pkg_cache'] = self._item(f"{self.pm['label']} Package Cache", str(cache_dir), size,
                                              f"Downloaded installation packages in {cache_dir}", True)

        # 4. Orphaned packages (dependencies nothing needs any more)
        if self.pm and self.pm.get('orphans_cmd'):
            orphans = pkgmgr.query(self.pm['orphans_cmd'], self.pm['parse_orphans']) or []
            if orphans:
                results['orphans'] = self._item(
                    f"Orphaned Packages ({len(orphans)})", "", UNKNOWN,
                    f"Unneeded dependencies: {', '.join(orphans[:8])}{'...' if len(orphans) > 8 else ''}",
                    True, packages=orphans)

        # 5. Systemd journal
        journal_size = 0
        try:
            out = subprocess.check_output(["journalctl", "--disk-usage"], stderr=subprocess.DEVNULL)
            # "Archived and active journals take up 1.2G in the file system."
            m = re.search(r"take up (\S+)", out.decode("utf-8", errors="ignore"))
            journal_size = parse_size(m[1]) if m else 0
            size_str = m[1] if m else "0 B"
        except Exception:
            size_str = "0 B"
        results['systemd_logs'] = self._item("Systemd Journal Logs", "/var/log/journal", max(journal_size, 0),
                                             "System services and boot logs (keeps the last day)", True)
        results['systemd_logs']['size_str'] = size_str

        # 6. Developer junk
        dev_paths = self._find_dev_junk()
        dev_size = sum(self.get_dir_size(Path(p)) for p in dev_paths)
        results['dev_junk'] = self._item(
            "Developer Build Artifacts", f"{len(dev_paths)} folders found", dev_size,
            f"Build artifacts (node_modules, target, .venv) in Projects/Home. Detected: "
            f"{', '.join([Path(p).parent.name + '/' + Path(p).name for p in dev_paths[:3]])}...",
            False, paths_list=dev_paths)

        if self.probe_host:
            results.update(self._scan_extras())
        return results

    def _find_dev_junk(self) -> list:
        search_dirs = [self.home / "Projects", self.home / "workspace", self.home / "Downloads", self.home]
        found = []
        for sdir in search_dirs:
            if sdir.exists() and sdir.is_dir():
                try:
                    for entry in sdir.iterdir():
                        if entry.is_dir() and not entry.name.startswith("."):
                            for sub, markers in DEV_JUNK_MARKERS.items():
                                path = entry / sub
                                # "build"/"target" are only junk next to a project file that produced them
                                if path.exists() and path.is_dir() and path.resolve() != RUNNING_VENV and (
                                        markers is None or any((entry / m).exists() for m in markers)):
                                    if str(path) not in found:
                                        found.append(str(path))
                except Exception:
                    pass
        return found

    def _scan_extras(self) -> dict:
        """Optional sources that exist only on some hosts: flatpak, podman/docker, snap."""
        results = {}
        if shutil.which("flatpak"):
            results['flatpak_unused'] = self._item(
                "Unused Flatpak Runtimes", "", UNKNOWN, "Runtimes and extensions no installed app uses", False)

        for tool in ("podman", "docker"):
            if not shutil.which(tool):
                continue
            try:
                res = subprocess.run([tool, "system", "df", "--format", "{{.Type}}\t{{.Reclaimable}}"],
                                     capture_output=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                continue
            if res.returncode != 0:
                continue  # e.g. no permission on the docker socket
            size = 0
            for line in res.stdout.decode(errors="ignore").splitlines():
                kind, _, rec = line.partition("\t")
                if "volume" not in kind.lower():  # prune without --volumes keeps volumes
                    size += max(parse_size(rec), 0)
            results['containers'] = self._item(
                f"{tool.capitalize()} Unused Data", tool, size,
                "Stopped containers, dangling images, unused networks, build cache (volumes kept). Size is an upper bound.",
                False, tool=tool)
            break

        if shutil.which("snap"):
            revs = self._disabled_snaps()
            if revs:
                size = sum(r['size'] for r in revs)
                results['snap_old'] = self._item(
                    f"Old Snap Revisions ({len(revs)})", "/var/lib/snapd/snaps", size,
                    ", ".join(f"{r['name']} r{r['rev']}" for r in revs[:6]), True, revisions=revs)
        return results

    def _disabled_snaps(self) -> list:
        try:
            out = subprocess.run(["snap", "list", "--all"], capture_output=True, timeout=30).stdout.decode()
        except (OSError, subprocess.SubprocessError):
            return []
        return parse_disabled_snaps(out)

    # ---- clean ---------------------------------------------------------------

    def clean(self, item_id: str, scan_details: dict, dry_run: bool = False, selected: list | None = None,
              use_trash: bool = True) -> tuple[bool, str]:
        """Clean one scanned item. `selected` narrows user_cache to some folders.
        `use_trash` moves user-owned data (dev junk) to the Trash so `marmot undo` can restore it."""
        details = scan_details.get(item_id)
        if not details:
            return False, "Item not found in scan details"

        path_str = details.get('path')

        if item_id == 'user_cache':
            cache_path = Path(path_str)
            if not cache_path.exists():
                return False, "Cache directory does not exist"
            children = details.get('children') or []
            targets = [c for c in children if selected is None or c['path'] in selected]
            if not children:  # scan found no folders (or old scan format): wipe the whole cache dir
                if dry_run:
                    return True, f"Would delete everything in {cache_path}"
                shutil.rmtree(cache_path, ignore_errors=True)
                os.makedirs(cache_path, exist_ok=True)
                trash.record("clean:user_cache", freed=details.get('size', 0))
                return True, "User caches cleaned successfully"
            freed = sum(c['size'] for c in targets)
            if dry_run:
                return True, (f"Would delete {len(targets)} cache folder(s), {self.format_size(freed)}: "
                              f"{', '.join(c['name'] for c in targets)}")
            for c in targets:
                p = Path(c['path'])
                if p.parent != cache_path:  # defence in depth: only direct children of ~/.cache
                    continue
                if p.is_dir() and not p.is_symlink():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
            trash.record("clean:user_cache", freed=freed, detail=", ".join(c['name'] for c in targets))
            return True, f"User caches cleaned successfully ({len(targets)} folder(s), {self.format_size(freed)})"

        elif item_id == 'trash':
            trash_path = Path(path_str)
            if not trash_path.exists():
                return False, "Trash directory does not exist"
            if dry_run:
                return True, f"Would permanently delete {details.get('size_str', '?')} from {trash_path}"
            shutil.rmtree(trash_path, ignore_errors=True)
            os.makedirs(trash_path / "files", exist_ok=True)
            os.makedirs(trash_path / "info", exist_ok=True)
            trash.record("clean:trash", freed=details.get('size', 0))
            return True, "Trash bin emptied successfully"

        elif item_id == 'pkg_cache':
            if not self.pm:
                return False, "Unsupported distribution: no supported package manager found."
            return self._root_action(self.pm['clean_cmd'](), dry_run, item_id, details,
                                     f"{self.pm['label']} packages cache cleaned successfully")

        elif item_id == 'orphans':
            names = details.get('packages') or []
            return self._root_action(self.pm['remove_orphans_cmd'](names), dry_run, item_id, details,
                                     f"Removed {len(names)} orphaned package(s)")

        elif item_id == 'systemd_logs':
            return self._root_action(["journalctl", "--vacuum-time=1d"], dry_run, item_id, details,
                                     "Systemd logs vacuumed", show_output=True)

        elif item_id == 'snap_old':
            argv = [x for r in details.get('revisions', []) for x in (r['name'], str(r['rev']))]
            return self._root_action(["sh", "-c", _SNAP_REMOVE, "sh", *argv], dry_run, item_id, details,
                                     f"Removed {len(argv) // 2} old snap revision(s)")

        elif item_id == 'flatpak_unused':
            return self._user_action(["flatpak", "uninstall", "--unused", "-y"], dry_run, item_id, details,
                                     "Unused Flatpak runtimes removed")

        elif item_id == 'containers':
            return self._user_action([details['tool'], "system", "prune", "-f"], dry_run, item_id, details,
                                     f"{details['tool'].capitalize()} unused data pruned")

        elif item_id == 'dev_junk':
            paths = details.get('paths_list', [])
            if dry_run:
                where = "to Trash" if use_trash else "permanently"
                return True, f"Would move {len(paths)} build folder(s) {where}: {', '.join(paths)}"
            trashed, cleaned_count = [], 0
            for p in paths:
                try:
                    if use_trash:
                        trashed.append({'name': trash.move_to_trash(p), 'path': p})
                    else:
                        shutil.rmtree(p, ignore_errors=True)
                    cleaned_count += 1
                except Exception:
                    pass
            trash.record("clean:dev_junk", freed=0 if use_trash else details.get('size', 0), trashed=trashed)
            if use_trash:
                return True, f"Moved {cleaned_count} build folder(s) to Trash (marmot undo restores them)"
            return True, f"Cleaned {cleaned_count} build folder(s)"

        return False, "Unknown item"

    def _root_action(self, cmd: list, dry_run: bool, item_id: str, details: dict, ok_msg: str,
                     show_output: bool = False) -> tuple[bool, str]:
        if dry_run:
            return True, f"Would run as root: {shlex.join(cmd)}"
        ok, via, out = run_root(cmd)
        if not ok:
            return False, f"Failed to execute. Sudo privileges required. Error: {out}"
        trash.record(f"clean:{item_id}", freed=max(details.get('size', 0), 0))
        return True, f"{ok_msg}{via}" + (f": {out}" if show_output and out else "")

    def _user_action(self, cmd: list, dry_run: bool, item_id: str, details: dict, ok_msg: str) -> tuple[bool, str]:
        if dry_run:
            return True, f"Would run: {shlex.join(cmd)}"
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=600)
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"Failed: {e}"
        if res.returncode != 0:
            return False, f"Failed: {res.stderr.decode(errors='ignore').strip()[-300:]}"
        trash.record(f"clean:{item_id}", freed=max(details.get('size', 0), 0))
        return True, ok_msg


def parse_disabled_snaps(out: str) -> list:
    """`snap list --all` rows whose Notes column says `disabled` -> [{name, rev, size}]."""
    revs = []
    for line in out.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 4 and "disabled" in cols[-1].split(","):
            name, rev = cols[0], cols[2]
            try:
                size = Path(f"/var/lib/snapd/snaps/{name}_{rev}.snap").stat().st_size
            except OSError:
                size = 0
            revs.append({'name': name, 'rev': rev, 'size': size})
    return revs
