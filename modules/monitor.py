import time
import os

class SystemMonitor:
    def __init__(self):
        self.last_cpu_idle = 0.0
        self.last_cpu_total = 0.0
        self.last_net_bytes = {} # interface: (rx_bytes, tx_bytes, time)
        
        # Initialize CPU values
        self.get_cpu_usage()
        # Initialize Network values
        self.get_network_io()
        
    def get_cpu_usage(self) -> float:
        try:
            with open('/proc/stat', 'r') as f:
                line = f.readline()
            parts = line.split()
            if len(parts) > 4:
                # user, nice, system, idle, iowait, irq, softirq, steal
                fields = [float(x) for x in parts[1:9]]
                idle = fields[3] + fields[4] # idle + iowait
                total = sum(fields)
                
                delta_idle = idle - self.last_cpu_idle
                delta_total = total - self.last_cpu_total
                
                self.last_cpu_idle = idle
                self.last_cpu_total = total
                
                if delta_total == 0:
                    return 0.0
                return (1.0 - (delta_idle / delta_total)) * 100.0
        except Exception:
            return 0.0

    def get_memory_info(self) -> dict:
        mem = {}
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        name = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        mem[name] = int(val) * 1024 # convert kB to bytes
            
            total = mem.get('MemTotal', 0)
            free = mem.get('MemFree', 0)
            avail = mem.get('MemAvailable', free)
            used = total - avail
            
            swap_total = mem.get('SwapTotal', 0)
            swap_free = mem.get('SwapFree', 0)
            swap_used = swap_total - swap_free
            
            return {
                'total': total,
                'used': used,
                'available': avail,
                'percent': (used / total * 100.0) if total > 0 else 0.0,
                'swap_total': swap_total,
                'swap_used': swap_used,
                'swap_percent': (swap_used / swap_total * 100.0) if swap_total > 0 else 0.0
            }
        except Exception:
            return {
                'total': 0, 'used': 0, 'available': 0, 'percent': 0.0,
                'swap_total': 0, 'swap_used': 0, 'swap_percent': 0.0
            }

    def get_network_io(self) -> dict:
        stats = {}
        now = time.time()
        try:
            with open('/proc/net/dev', 'r') as f:
                lines = f.readlines()
            for line in lines[2:]: # skip headers
                if ':' not in line:
                    continue
                parts = line.split(':')
                if len(parts) < 2:
                    continue
                iface = parts[0].strip()
                if iface == 'lo':
                    continue
                data = parts[1].split()
                if len(data) >= 9:
                    rx = int(data[0]) # rx_bytes
                    tx = int(data[8]) # tx_bytes
                    
                    if iface in self.last_net_bytes:
                        prev_rx, prev_tx, prev_time = self.last_net_bytes[iface]
                        dt = now - prev_time
                        if dt > 0:
                            rx_speed = (rx - prev_rx) / dt # bytes/sec
                            tx_speed = (tx - prev_tx) / dt # bytes/sec
                        else:
                            rx_speed, tx_speed = 0.0, 0.0
                    else:
                        rx_speed, tx_speed = 0.0, 0.0
                    
                    self.last_net_bytes[iface] = (rx, tx, now)
                    stats[iface] = {
                        'rx_speed': rx_speed, # bytes/sec
                        'tx_speed': tx_speed, # bytes/sec
                        'rx_total': rx,
                        'tx_total': tx
                    }
            return stats
        except Exception:
            return {}

    def get_temperature(self) -> float | None:
        try:
            base_dir = '/sys/class/thermal'
            if os.path.exists(base_dir):
                for d in os.listdir(base_dir):
                    if d.startswith('thermal_zone'):
                        type_path = os.path.join(base_dir, d, 'type')
                        temp_path = os.path.join(base_dir, d, 'temp')
                        if os.path.exists(type_path) and os.path.exists(temp_path):
                            with open(type_path, 'r') as f:
                                t_type = f.read().strip()
                            if 'cpu' in t_type.lower() or 'pkg' in t_type.lower() or 'acpitz' in t_type.lower():
                                with open(temp_path, 'r') as f:
                                    temp_raw = float(f.read().strip())
                                return temp_raw / 1000.0
                                
            hwmon_dir = '/sys/class/hwmon'
            if os.path.exists(hwmon_dir):
                for h in os.listdir(hwmon_dir):
                    h_path = os.path.join(hwmon_dir, h)
                    name_path = os.path.join(h_path, 'name')
                    if os.path.exists(name_path):
                        with open(name_path, 'r') as f:
                            name = f.read().strip()
                        if 'temp' in name or 'core' in name or 'cpu' in name:
                            for file in os.listdir(h_path):
                                if file.startswith('temp') and file.endswith('_input'):
                                    with open(os.path.join(h_path, file), 'r') as f:
                                        temp_raw = float(f.read().strip())
                                    return temp_raw / 1000.0
        except Exception:
            pass
        return None

    def get_battery_info(self) -> dict:
        try:
            power_dir = '/sys/class/power_supply'
            if os.path.exists(power_dir):
                for supply in os.listdir(power_dir):
                    if supply.startswith('BAT'):
                        bat_path = os.path.join(power_dir, supply)
                        cap_path = os.path.join(bat_path, 'capacity')
                        stat_path = os.path.join(bat_path, 'status')
                        power_path = os.path.join(bat_path, 'power_now')
                        volt_path = os.path.join(bat_path, 'voltage_now')
                        current_path = os.path.join(bat_path, 'current_now')
                        
                        cap = None
                        status = "Unknown"
                        power = None
                        
                        if os.path.exists(cap_path):
                            with open(cap_path, 'r') as f:
                                cap = int(f.read().strip())
                        if os.path.exists(stat_path):
                            with open(stat_path, 'r') as f:
                                status = f.read().strip()
                                
                        if os.path.exists(power_path):
                            with open(power_path, 'r') as f:
                                power = float(f.read().strip()) / 1000000.0
                        elif os.path.exists(current_path) and os.path.exists(volt_path):
                            with open(current_path, 'r') as f1, open(volt_path, 'r') as f2:
                                current = float(f1.read().strip())
                                voltage = float(f2.read().strip())
                                power = (current * voltage) / 1000000000000.0
                                
                        return {
                            'present': True,
                            'capacity': cap,
                            'status': status,
                            'power': power
                        }
        except Exception:
            pass
        return {'present': False, 'capacity': None, 'status': 'Unknown', 'power': None}

    def get_disk_usage(self) -> list:
        partitions = []
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3:
                        device = parts[0]
                        mountpoint = parts[1]
                        fstype = parts[2]
                        if device.startswith('/dev/') and not device.startswith('/dev/loop') and not mountpoint.startswith('/boot'):
                            statvfs = os.statvfs(mountpoint)
                            total = statvfs.f_blocks * statvfs.f_frsize
                            free = statvfs.f_bfree * statvfs.f_frsize
                            avail = statvfs.f_bavail * statvfs.f_frsize
                            used = total - free
                            percent = (used / total * 100.0) if total > 0 else 0.0
                            partitions.append({
                                'device': device,
                                'mountpoint': mountpoint,
                                'fstype': fstype,
                                'total': total,
                                'used': used,
                                'available': avail,
                                'percent': percent
                            })
            return partitions
        except Exception:
            return []
