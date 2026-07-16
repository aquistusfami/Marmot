import time
from modules.monitor import SystemMonitor

def test():
    monitor = SystemMonitor()
    
    print("=== Testing SystemMonitor ===")
    
    # Wait 1 second to get a valid CPU delta
    print("Waiting 1s for CPU statistics...")
    time.sleep(1)
    
    # 1. CPU
    cpu = monitor.get_cpu_usage()
    temp = monitor.get_temperature()
    print(f"CPU Usage: {cpu:.2f}%")
    print(f"CPU Temp: {f'{temp:.1f}°C' if temp is not None else 'N/A'}")
    print("-" * 30)
    
    # 2. Memory
    mem = monitor.get_memory_info()
    print("Memory Info:")
    print(f"  RAM Total: {mem['total'] / (1024**3):.2f} GB")
    print(f"  RAM Used: {mem['used'] / (1024**3):.2f} GB ({mem['percent']:.1f}%)")
    print(f"  RAM Available: {mem['available'] / (1024**3):.2f} GB")
    print(f"  Swap Total: {mem['swap_total'] / (1024**3):.2f} GB")
    print(f"  Swap Used: {mem['swap_used'] / (1024**3):.2f} GB ({mem['swap_percent']:.1f}%)")
    print("-" * 30)
    
    # 3. Network
    print("Network Interfaces:")
    net = monitor.get_network_io()
    if not net:
        print("  No active interfaces (except loopback) or error reading network stats.")
    for iface, data in net.items():
        rx = data['rx_speed'] / 1024.0
        tx = data['tx_speed'] / 1024.0
        print(f"  {iface}: Download Speed: {rx:.2f} KB/s, Upload Speed: {tx:.2f} KB/s")
        print(f"  {iface}: Total Downloaded: {data['rx_total'] / (1024**2):.2f} MB, Total Uploaded: {data['tx_total'] / (1024**2):.2f} MB")
    print("-" * 30)
    
    # 4. Battery
    bat = monitor.get_battery_info()
    print("Battery Info:")
    if bat['present']:
        print(f"  Capacity: {bat['capacity']}%")
        print(f"  Status: {bat['status']}")
        if bat['power'] is not None:
            print(f"  Power Draw: {bat['power']:.2f} W")
    else:
        print("  Battery not present (AC powered desktop/VM).")
    print("-" * 30)
    
    # 5. Disk Usage
    disks = monitor.get_disk_usage()
    print("Disk Partition Usage:")
    for d in disks:
        print(f"  {d['mountpoint']} ({d['device']}): {d['used'] / (1024**3):.2f} GB / {d['total'] / (1024**3):.2f} GB ({d['percent']:.1f}%)")
    print("=" * 30)

if __name__ == "__main__":
    test()
