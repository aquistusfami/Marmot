import os
import stat
from collections.abc import Callable
from pathlib import Path


class ScanCancelled(Exception):
    pass


class DiskAnalyzer:
    """ncdu-like sizes. Every directory size computed is cached, so going into a child or back
    to the parent after a scan is instant. `invalidate()` drops the cache (Rescan, after cleaning)."""

    def __init__(self):
        self.current_path = Path.home()
        self._cache: dict[str, int] = {}

    def set_path(self, path_str: str):
        path = Path(path_str)
        if path.exists() and path.is_dir():
            self.current_path = path

    def invalidate(self) -> None:
        self._cache.clear()

    def format_size(self, size_bytes: int) -> str:
        if size_bytes == 0:
            return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_name) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_name[i]}"

    def _recursive_size(self, path_str: str, cancelled: Callable[[], bool] | None = None) -> int:
        """Apparent size of a file, or of a directory tree (symlinks count 0, other filesystems skipped)."""
        cached = self._cache.get(path_str)
        if cached is not None:
            return cached
        try:
            st = os.lstat(path_str)
        except OSError:
            return 0
        if stat.S_ISLNK(st.st_mode):
            return 0
        if not stat.S_ISDIR(st.st_mode):
            return st.st_size
        return self._dir_size(path_str, st.st_dev, cancelled)

    def _dir_size(self, path_str: str, dev: int, cancelled) -> int:
        cached = self._cache.get(path_str)
        if cached is not None:
            return cached
        if cancelled and cancelled():
            raise ScanCancelled
        total = 0
        try:
            with os.scandir(path_str) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            # like `du -x`: don't wander into /proc, network mounts, other disks
                            if entry.stat(follow_symlinks=False).st_dev == dev:
                                total += self._dir_size(entry.path, dev, cancelled)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
        self._cache[path_str] = total
        return total

    def scan_current(self, progress: Callable[[int, int, str], None] | None = None,
                     cancelled: Callable[[], bool] | None = None) -> list:
        """Sizes of the current directory's entries, biggest first.
        `progress(done, total, name)` is called per entry; raises ScanCancelled if `cancelled()` turns true."""
        items = []
        try:
            entries = list(os.scandir(self.current_path))
        except Exception:
            return items
        for n, entry in enumerate(entries):
            if progress:
                progress(n, len(entries), entry.name)
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
                size = self._recursive_size(entry.path, cancelled) if is_directory else entry.stat().st_size
                items.append({
                    'name': entry.name,
                    'path': entry.path,
                    'size': size,
                    'size_str': self.format_size(size),
                    'is_dir': is_directory
                })
            except OSError:
                pass
        items.sort(key=lambda x: x['size'], reverse=True)
        total = sum(i['size'] for i in items) or 1
        for i in items:
            i['percent'] = i['size'] * 100 / total
        self._cache[str(self.current_path)] = sum(i['size'] for i in items)
        return items
