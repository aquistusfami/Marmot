import subprocess

class SystemOptimizer:
    def __init__(self):
        pass
        
    def get_optimizations(self) -> list:
        return [
            {
                'id': 'drop_caches',
                'name': "Drop RAM Memory Cache",
                'desc': "Frees system page cache, dentries, and inodes. Safe to run at any time.",
                'requires_sudo': True
            },
            {
                'id': 'flush_dns',
                'name': "Flush DNS Cache",
                'desc': "Flushes resolvectl or nscd local DNS query caches. Useful for resolving connection issues.",
                'requires_sudo': True
            },
            {
                'id': 'reset_services',
                'name': "Reset Failed Systemd Services",
                'desc': "Resets failed state of all systemd services that ran into errors.",
                'requires_sudo': True
            },
            {
                'id': 'swap_reset',
                'name': "Reclaim Swap space",
                'desc': "Flushes data in swap back into physical RAM. Safe if free memory is sufficient.",
                'requires_sudo': True
            }
        ]

    def run_optimization(self, opt_id: str) -> tuple[bool, str]:
        if opt_id == 'drop_caches':
            try:
                # Sync first
                subprocess.run(["sync"], check=True)
                # Drop caches
                cmd = ["pkexec", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"]
                subprocess.run(cmd, check=True)
                return True, "RAM page cache dropped successfully"
            except Exception:
                try:
                    subprocess.run(["sudo", "-n", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"], check=True)
                    return True, "RAM page cache dropped successfully (via sudo)"
                except Exception as e:
                    return False, f"Failed. Sudo privileges required. Error: {str(e)}"
                    
        elif opt_id == 'flush_dns':
            # Check resolved
            resolved_active = False
            try:
                subprocess.run(["systemctl", "is-active", "--quiet", "systemd-resolved"], check=True)
                resolved_active = True
            except Exception:
                pass
                
            if resolved_active:
                try:
                    subprocess.run(["pkexec", "resolvectl", "flush-caches"], check=True)
                    return True, "DNS cache flushed via resolvectl"
                except Exception:
                    try:
                        subprocess.run(["sudo", "-n", "resolvectl", "flush-caches"], check=True)
                        return True, "DNS cache flushed via resolvectl (via sudo)"
                    except Exception as e:
                        return False, f"Failed to run resolvectl. Error: {str(e)}"
            else:
                # Try nscd
                try:
                    subprocess.run(["pkexec", "systemctl", "restart", "nscd"], check=True)
                    return True, "DNS cache flushed by restarting nscd service"
                except Exception:
                    try:
                        subprocess.run(["sudo", "-n", "systemctl", "restart", "nscd"], check=True)
                        return True, "DNS cache flushed by restarting nscd service (via sudo)"
                    except Exception as e:
                        return False, f"Failed to flush DNS cache. Neither systemd-resolved nor nscd is running. Error: {str(e)}"
                        
        elif opt_id == 'reset_services':
            try:
                subprocess.run(["pkexec", "systemctl", "reset-failed"], check=True)
                return True, "Failed Systemd services status reset successfully"
            except Exception:
                try:
                    subprocess.run(["sudo", "-n", "systemctl", "reset-failed"], check=True)
                    return True, "Failed Systemd services status reset successfully (via sudo)"
                except Exception as e:
                    return False, f"Failed. Sudo privileges required. Error: {str(e)}"
                    
        elif opt_id == 'swap_reset':
            # Check memory first
            try:
                # Get free memory and swap used
                with open("/proc/meminfo", "r") as f:
                    meminfo = f.read()
                lines = meminfo.split("\n")
                mem_free = 0
                swap_used = 0
                for line in lines:
                    if "MemAvailable:" in line or "MemFree:" in line and mem_free == 0:
                        mem_free = int(line.split()[1]) * 1024 # B
                    if "SwapTotal:" in line:
                        st = int(line.split()[1]) * 1024
                    if "SwapFree:" in line:
                        sf = int(line.split()[1]) * 1024
                        swap_used = st - sf
                        
                if mem_free < swap_used:
                    return False, f"Safety warning: Free RAM ({mem_free // 1024 // 1024}MB) is less than Swap used ({swap_used // 1024 // 1024}MB). Resetting swap might crash your system!"
                    
                # Run swapoff and swapon
                subprocess.run(["pkexec", "swapoff", "-a"], check=True)
                subprocess.run(["pkexec", "swapon", "-a"], check=True)
                return True, "Swap space reclaimed and cycled successfully"
            except Exception:
                try:
                    subprocess.run(["sudo", "-n", "swapoff", "-a"], check=True)
                    subprocess.run(["sudo", "-n", "swapon", "-a"], check=True)
                    return True, "Swap space reclaimed and cycled successfully (via sudo)"
                except Exception as e:
                    return False, f"Failed. Sudo privileges required. Error: {str(e)}"
                    
        return False, "Unknown optimization ID"
