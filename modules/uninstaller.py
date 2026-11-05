import subprocess
import os
from pathlib import Path

from modules import pkgmgr

# Only direct children of these dirs (relative to $HOME) may be deleted as remnants.
REMNANT_PARENTS = (".config", ".local/share", ".cache")


class PackageUninstaller:
    def __init__(self, backend: str | None = None):
        self.home = Path.home()
        self.pm = pkgmgr.get(backend)

    def list_installed_packages(self, search_query: str = "") -> list:
        packages = []
        if not self.pm:
            return packages
        try:
            process = subprocess.Popen(self.pm['list_cmd'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            out, _ = process.communicate()
            q = search_query.lower()
            for pkg in self.pm['parse_list'](out.decode("utf-8", errors="ignore")):
                if not q or q in pkg['name'].lower() or q in pkg['summary'].lower():
                    packages.append(pkg)
            packages.sort(key=lambda x: x['name'])
        except Exception:
            pass
        return packages[:60] # limit for smooth TUI scrolling

    def preview_removal(self, package_name: str) -> list | None:
        """Packages the package manager would remove (dependants/orphans included), or None on error."""
        if not self.pm:
            return None
        try:
            res = subprocess.run(self.pm['preview_cmd'](package_name), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                return None
            return self.pm['parse_preview'](res.stdout.decode("utf-8", errors="ignore"))
        except Exception:
            return None

    def _remnant_parents(self) -> list:
        return [self.home / d for d in REMNANT_PARENTS]

    def find_remnants(self, package_name: str) -> list:
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
            for root, dirs, files in os.walk(folder):
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

    def uninstall(self, package_name: str, delete_remnants: list = None) -> tuple[bool, str]:
        success = False
        msg = ""
        if not self.pm:
            return False, "Unsupported distribution: no apt or pacman found."
        try:
            cmd = ["pkexec", *self.pm['remove_cmd'](package_name)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0:
                success = True
                msg = f"Package {package_name} purged successfully."
            else:
                cmd = ["sudo", "-n", *self.pm['remove_cmd'](package_name)]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res.returncode == 0:
                    success = True
                    msg = f"Package {package_name} purged successfully (via sudo)."
                else:
                    msg = f"Failed to purge package: {res.stderr.decode('utf-8').strip()}"
        except Exception as e:
            msg = f"Error during purge execution: {str(e)}"

        if success and delete_remnants:
            import shutil
            deleted_paths = []
            for rpath in delete_remnants:
                if not self.is_safe_remnant(rpath):
                    continue
                try:
                    shutil.rmtree(rpath, ignore_errors=True)
                    deleted_paths.append(rpath)
                except Exception:
                    pass
            if deleted_paths:
                msg += f" Cleared user config remnants: {', '.join([os.path.basename(p) for p in deleted_paths])}."
                
        return success, msg
