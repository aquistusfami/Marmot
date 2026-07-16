import subprocess
import os
from pathlib import Path

class PackageUninstaller:
    def __init__(self):
        self.home = Path.home()
        
    def list_installed_packages(self, search_query: str = "") -> list:
        packages = []
        try:
            cmd = ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${binary:Summary}\n"]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            out, _ = process.communicate()
            
            lines = out.decode("utf-8", errors="ignore").strip().split("\n")
            search_query_lower = search_query.lower()
            for line in lines:
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    name, ver, summary = parts[0], parts[1], parts[2]
                    if not search_query or search_query_lower in name.lower() or search_query_lower in summary.lower():
                        packages.append({
                            'name': name,
                            'version': ver,
                            'summary': summary
                        })
            packages.sort(key=lambda x: x['name'])
        except Exception:
            pass
        return packages[:60] # limit for smooth TUI scrolling

    def find_remnants(self, package_name: str) -> list:
        remnants = []
        possible_dirs = [
            self.home / ".config" / package_name,
            self.home / ".local" / "share" / package_name,
            self.home / ".cache" / package_name,
            self.home / ".var" / "app" / package_name
        ]
        
        check_parent = [self.home / ".config", self.home / ".local" / "share", self.home / ".cache"]
        for pdir in check_parent:
            if pdir.exists() and pdir.is_dir():
                try:
                    for entry in pdir.iterdir():
                        if entry.is_dir() and package_name.lower() in entry.name.lower():
                            if entry not in possible_dirs:
                                possible_dirs.append(entry)
                except Exception:
                    pass

        for folder in possible_dirs:
            if folder.exists() and folder.is_dir():
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
        try:
            cmd = ["pkexec", "apt-get", "purge", "-y", package_name]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0:
                success = True
                msg = f"Package {package_name} purged successfully."
            else:
                cmd = ["sudo", "-n", "apt-get", "purge", "-y", package_name]
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
                try:
                    shutil.rmtree(rpath, ignore_errors=True)
                    deleted_paths.append(rpath)
                except Exception:
                    pass
            if deleted_paths:
                msg += f" Cleared user config remnants: {', '.join([os.path.basename(p) for p in deleted_paths])}."
                
        return success, msg
