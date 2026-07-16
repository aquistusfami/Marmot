import os
import shutil
import subprocess
from pathlib import Path

class SystemCleaner:
    def __init__(self):
        self.home = Path.home()
        
    def get_dir_size(self, path: Path) -> int:
        total_size = 0
        try:
            if path.is_file():
                return path.stat().st_size
            for root, dirs, files in os.walk(path):
                # Handle permission errors gracefully
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
        if size_bytes == 0:
            return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_name) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_name[i]}"

    def scan(self) -> dict:
        results = {}
        
        # 1. User Cache (~/.cache)
        cache_path = self.home / ".cache"
        cache_size = self.get_dir_size(cache_path)
        results['user_cache'] = {
            'name': "User Caches",
            'path': str(cache_path),
            'size': cache_size,
            'size_str': self.format_size(cache_size),
            'desc': "Temporary application cache files (Chrome, Firefox, Spotify, etc.)",
            'requires_sudo': False
        }
        
        # 2. Trash (~/.local/share/Trash)
        trash_path = self.home / ".local" / "share" / "Trash"
        trash_size = self.get_dir_size(trash_path)
        results['trash'] = {
            'name': "System Trash",
            'path': str(trash_path),
            'size': trash_size,
            'size_str': self.format_size(trash_size),
            'desc': "Files in your trash bin",
            'requires_sudo': False
        }
        
        # 3. Apt Cache (/var/cache/apt/archives)
        apt_path = Path("/var/cache/apt/archives")
        apt_size = 0
        if apt_path.exists():
            # Get size of all .deb packages in archives
            for f in apt_path.glob("*.deb"):
                try:
                    apt_size += f.stat().st_size
                except OSError:
                    pass
        results['apt_cache'] = {
            'name': "Apt Package Cache",
            'path': str(apt_path),
            'size': apt_size,
            'size_str': self.format_size(apt_size),
            'desc': "Downloaded Debian installation packages (.deb)",
            'requires_sudo': True
        }
        
        # 4. Systemd Journal Logs
        journal_size = 0
        try:
            out = subprocess.check_output(["journalctl", "--disk-usage"], stderr=subprocess.DEVNULL)
            # Example output: "Archived and active journals take up 1.2GB in the file system."
            parts = out.decode("utf-8").split()
            # Try to find a size part
            for part in parts:
                if "take" in part or "up" in part:
                    continue
                if "B" in part or "KB" in part or "MB" in part or "GB" in part:
                    # found size string
                    results['systemd_logs'] = {
                        'name': "Systemd Journal Logs",
                        'path': "/var/log/journal",
                        'size': 1, # placeholder greater than 0
                        'size_str': part,
                        'desc': "System services and boot logs",
                        'requires_sudo': True
                    }
                    break
        except Exception:
            pass
            
        if 'systemd_logs' not in results:
            results['systemd_logs'] = {
                'name': "Systemd Journal Logs",
                'path': "/var/log/journal",
                'size': 0,
                'size_str': "0 B",
                'desc': "System services and boot logs",
                'requires_sudo': True
            }
            
        # 5. Developer Junk (Scan first level of user folders for node_modules, target, .venv)
        dev_size = 0
        dev_paths = []
        # To keep scan fast, we search in standard locations
        search_dirs = [self.home / "Projects", self.home / "workspace", self.home / "Downloads", self.home]
        
        found_folders = []
        for sdir in search_dirs:
            if sdir.exists() and sdir.is_dir():
                try:
                    # Scan depth 2 to keep it responsive
                    for entry in sdir.iterdir():
                        if entry.is_dir() and not entry.name.startswith("."):
                            # Check standard build folders
                            for sub in ["node_modules", "target", ".venv", "__pycache__", "build"]:
                                path = entry / sub
                                if path.exists() and path.is_dir():
                                    found_folders.append(path)
                except Exception:
                    pass
        
        # Scan inside projects too if they are top level
        for folder in found_folders:
            sz = self.get_dir_size(folder)
            dev_size += sz
            dev_paths.append(str(folder))
            
        results['dev_junk'] = {
            'name': "Developer Build Artifacts",
            'path': f"{len(dev_paths)} folders found",
            'size': dev_size,
            'size_str': self.format_size(dev_size),
            'desc': f"Build artifacts (node_modules, target, .venv) in Projects/Home. Detected: {', '.join([Path(p).parent.name + '/' + Path(p).name for p in dev_paths[:3]])}...",
            'paths_list': dev_paths,
            'requires_sudo': False
        }
        
        return results

    def clean(self, item_id: str, scan_details: dict) -> tuple[bool, str]:
        """Cleans specific item, returns (success, message)"""
        details = scan_details.get(item_id)
        if not details:
            return False, "Item not found in scan details"
            
        path_str = details.get('path')
        
        # 1. User Cache
        if item_id == 'user_cache':
            cache_path = Path(path_str)
            if cache_path.exists():
                shutil.rmtree(cache_path, ignore_errors=True)
                os.makedirs(cache_path, exist_ok=True)
                return True, "User caches cleaned successfully"
            return False, "Cache directory does not exist"
            
        # 2. Trash
        elif item_id == 'trash':
            trash_path = Path(path_str)
            if trash_path.exists():
                # delete files under Trash/files and Trash/info
                shutil.rmtree(trash_path, ignore_errors=True)
                os.makedirs(trash_path / "files", exist_ok=True)
                os.makedirs(trash_path / "info", exist_ok=True)
                return True, "Trash bin emptied successfully"
            return False, "Trash directory does not exist"
            
        # 3. Apt Cache
        elif item_id == 'apt_cache':
            # run apt-get clean (requires sudo)
            try:
                # We try using pkexec or sudo -n (non-interactive).
                # If it fails, suggest running as root
                cmd = ["pkexec", "apt-get", "clean"]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return True, "Apt packages cache cleaned successfully"
            except Exception:
                try:
                    # Try direct sudo if user is in sudoers without password or in terminal
                    subprocess.run(["sudo", "-n", "apt-get", "clean"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    return True, "Apt packages cache cleaned successfully (via sudo)"
                except Exception as e:
                    return False, f"Failed to execute. Sudo privileges required. Error: {str(e)}"
                    
        # 4. Systemd Logs
        elif item_id == 'systemd_logs':
            try:
                # Vacuum journalctl to 1 day
                cmd = ["pkexec", "journalctl", "--vacuum-time=1d"]
                res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return True, f"Systemd logs vacuumed: {res.stdout.decode('utf-8').strip()}"
            except Exception:
                try:
                    res = subprocess.run(["sudo", "-n", "journalctl", "--vacuum-time=1d"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    return True, f"Systemd logs vacuumed (via sudo): {res.stdout.decode('utf-8').strip()}"
                except Exception as e:
                    return False, f"Failed to execute. Sudo privileges required. Error: {str(e)}"
                    
        # 5. Developer Junk
        elif item_id == 'dev_junk':
            paths = details.get('paths_list', [])
            cleaned_count = 0
            for p in paths:
                try:
                    shutil.rmtree(p, ignore_errors=True)
                    cleaned_count += 1
                except Exception:
                    pass
            return True, f"Cleaned {cleaned_count} build folder(s)"
            
        return False, "Unknown item"
