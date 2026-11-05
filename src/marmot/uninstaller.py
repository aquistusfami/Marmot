import os
import subprocess
from pathlib import Path

from marmot import pkgmgr, trash

# Only direct children of these dirs (relative to $HOME) may be deleted as remnants.
REMNANT_PARENTS = (".config", ".local/share", ".cache")


class PackageUninstaller:
    def __init__(self, backend: str | None = None):
        self.home = Path.home()
        self.pm = pkgmgr.get(backend)
        self.flatpak = pkgmgr.flatpak() if backend is None else None

    def _list(self, pm: dict, source: str) -> list:
        process = subprocess.Popen(pm['list_cmd'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        out, _ = process.communicate()
        return [{**p, 'source': source} for p in pm['parse_list'](out.decode("utf-8", errors="ignore"))]

    def list_installed_packages(self, search_query: str = "") -> list:
        packages = []
        q = search_query.lower()
        for pm, source in ((self.pm, 'system'), (self.flatpak, 'flatpak')):
            if not pm:
                continue
            try:
                packages += [p for p in self._list(pm, source)
                             if not q or q in p['name'].lower() or q in p['summary'].lower()]
            except Exception:
                pass
        packages.sort(key=lambda x: x['name'])
        return packages[:60] # limit for smooth TUI scrolling

    def preview_removal(self, package_name: str, source: str = 'system') -> list | None:
        """Packages the package manager would remove (dependants/orphans included), or None on error."""
        if source == 'flatpak':
            return [package_name] if self.flatpak else None
        if not self.pm:
            return None
        # exit codes are not trusted (dnf --assumeno always "fails"): an empty parse means it would not work
        return pkgmgr.query(self.pm['preview_cmd'](package_name), self.pm['parse_preview'])

    def _remnant_parents(self) -> list:
        return [self.home / d for d in REMNANT_PARENTS]

    def find_remnants(self, package_name: str, source: str = 'system') -> list:
        if source == 'flatpak':
            return []  # `flatpak uninstall --delete-data` already removes ~/.var/app/<id>
        # Exact (case-insensitive) name match only: a substring match made "git" hit ~/.config/gitkraken.
        want = package_name.lower()
        folders = []
        for pdir in self._remnant_parents():
            if pdir.exists() and pdir.is_dir():
                try:
                    for entry in pdir.iterdir():
                        if entry.name.lower() == want and entry.is_dir() and entry not in folders:
                            folders.append(entry)
                except Exception:
                    pass

        remnants = []
        for folder in folders:
            size = 0
            for root, _dirs, files in os.walk(folder):
                for f in files:
                    try:
                        size += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
            remnants.append({
                'path': str(folder),
                'size': size,
                'size_str': self.format_size(size)
            })
        return remnants

    def is_safe_remnant(self, path_str: str) -> bool:
        path = Path(path_str)
        return path.parent in self._remnant_parents() and not path.is_symlink()

    def format_size(self, size_bytes: int) -> str:
        if size_bytes == 0:
            return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_name) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_name[i]}"

    def uninstall(self, package_name: str, delete_remnants: list = None, source: str = 'system') -> tuple[bool, str]:
        success = False
        msg = ""
        pm = self.flatpak if source == 'flatpak' else self.pm
        if not pm:
            return False, "Unsupported distribution: no supported package manager found."
        if not pm['privileged']:
            res = subprocess.run(pm['remove_cmd'](package_name), capture_output=True)
            if res.returncode != 0:
                return False, f"Failed to remove: {res.stderr.decode('utf-8', errors='ignore').strip()}"
            trash.record("uninstall", detail=f"{source}:{package_name}")
            return True, f"{pm['label']} app {package_name} removed (with its data)."
        try:
            cmd = ["pkexec", *self.pm['remove_cmd'](package_name)]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode == 0:
                success = True
                msg = f"Package {package_name} purged successfully."
            else:
                cmd = ["sudo", "-n", *self.pm['remove_cmd'](package_name)]
                res = subprocess.run(cmd, capture_output=True)
                if res.returncode == 0:
                    success = True
                    msg = f"Package {package_name} purged successfully (via sudo)."
                else:
                    msg = f"Failed to purge package: {res.stderr.decode('utf-8').strip()}"
        except Exception as e:
            msg = f"Error during purge execution: {str(e)}"

        if success:
            trashed = []
            for rpath in delete_remnants or []:
                if not self.is_safe_remnant(rpath):
                    continue
                try:
                    trashed.append({'name': trash.move_to_trash(rpath), 'path': rpath})
                except Exception:
                    pass
            if trashed:
                msg += (f" Moved remnants to Trash (marmot undo restores them): "
                        f"{', '.join(os.path.basename(t['path']) for t in trashed)}.")
            trash.record("uninstall", trashed=trashed, detail=f"system:{package_name}")

        return success, msg
