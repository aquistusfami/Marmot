import os
from pathlib import Path

class DiskAnalyzer:
    def __init__(self):
        self.current_path = Path.home()
        
    def set_path(self, path_str: str):
        path = Path(path_str)
        if path.exists() and path.is_dir():
            self.current_path = path

    def format_size(self, size_bytes: int) -> str:
        if size_bytes == 0:
            return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_name) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_name[i]}"

    def _recursive_size(self, path_str: str) -> int:
        import stat
        total = 0
        try:
            st = os.lstat(path_str)
            if stat.S_ISREG(st.st_mode):
                return st.st_size
            elif stat.S_ISLNK(st.st_mode):
                return 0
                
            for root, dirs, files in os.walk(path_str):
                for f in files:
                    try:
                        fp = os.path.join(root, f)
                        fst = os.lstat(fp)
                        if not stat.S_ISLNK(fst.st_mode):
                            total += fst.st_size
                    except OSError:
                        pass
        except Exception:
            pass
        return total

    def scan_current(self) -> list:
        items = []
        try:
            for entry in os.scandir(self.current_path):
                try:
                    is_directory = entry.is_dir(follow_symlinks=False)
                    if is_directory:
                        size = self._recursive_size(entry.path)
                    else:
                        size = entry.stat().st_size
                        
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
        except Exception:
            pass
        return items
