import os
import sys
import time
from pathlib import Path

# Add project root to path so we can import modules
sys.path.append(str(Path(__file__).parent.parent))

from modules.optimizer import SystemOptimizer

def get_mem_stats():
    stats = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split()
                if not parts:
                    continue
                name = parts[0].strip(":")
                val = int(parts[1]) * 1024 # Convert KB to bytes
                stats[name] = val
    except Exception as e:
        print(f"Error reading meminfo: {e}")
    return stats

def run_benchmark():
    optimizer = SystemOptimizer()
    report = []
    
    report.append("# Marmot Optimizer Performance & Impact Evaluation Report")
    report.append(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("Operating System: Debian GNU/Linux\n")
    
    report.append("This report evaluates the execution performance and system resource impact of each optimization task provided by the Marmot Optimizer module.\n")
    
    # ------------------ TEST 1: Drop Caches ------------------
    report.append("## 1. RAM Page Cache Optimization (`drop_caches`)")
    mem_before = get_mem_stats()
    
    t0 = time.time()
    success, msg = optimizer.run_optimization("drop_caches")
    t_elapsed = time.time() - t0
    
    mem_after = get_mem_stats()
    
    report.append(f"- **Execution Status**: {'[SUCCESS] ✅' if success else '[FAILED] ❌'}")
    report.append(f"- **Message**: `{msg}`")
    report.append(f"- **Execution Time**: `{t_elapsed:.4f} seconds`")
    
    if success and "Cached" in mem_before and "Cached" in mem_after:
        cached_diff = mem_before["Cached"] - mem_after["Cached"]
        avail_diff = mem_after.get("MemAvailable", 0) - mem_before.get("MemAvailable", 0)
        
        report.append(f"- **Memory Cache Before**: `{mem_before['Cached'] / 1024 / 1024:.2f} MB`")
        report.append(f"- **Memory Cache After**: `{mem_after['Cached'] / 1024 / 1024:.2f} MB`")
        report.append(f"- **Reclaimed Cache Memory**: **`{cached_diff / 1024 / 1024:.2f} MB`**")
        report.append(f"- **System Available RAM Change**: **`{avail_diff / 1024 / 1024:+.2f} MB`**")
    report.append("\n" + "-"*40 + "\n")
    
    # ------------------ TEST 2: Flush DNS ------------------
    report.append("## 2. DNS Resolution Cache Optimization (`flush_dns`)")
    t0 = time.time()
    success, msg = optimizer.run_optimization("flush_dns")
    t_elapsed = time.time() - t0
    
    report.append(f"- **Execution Status**: {'[SUCCESS] ✅' if success else '[FAILED] ❌'}")
    report.append(f"- **Message**: `{msg}`")
    report.append(f"- **Execution Time**: `{t_elapsed:.4f} seconds`")
    report.append("\n" + "-"*40 + "\n")
    
    # ------------------ TEST 3: Reset Services ------------------
    report.append("## 3. Systemd Services Reset (`reset_services`)")
    t0 = time.time()
    success, msg = optimizer.run_optimization("reset_services")
    t_elapsed = time.time() - t0
    
    report.append(f"- **Execution Status**: {'[SUCCESS] ✅' if success else '[FAILED] ❌'}")
    report.append(f"- **Message**: `{msg}`")
    report.append(f"- **Execution Time**: `{t_elapsed:.4f} seconds`")
    report.append("\n" + "-"*40 + "\n")
    
    # ------------------ TEST 4: Reclaim Swap ------------------
    report.append("## 4. Swap Space Reclaiming (`swap_reset`)")
    mem_before = get_mem_stats()
    
    # Calculate swap used before
    swap_before_used = 0
    if "SwapTotal" in mem_before and "SwapFree" in mem_before:
        swap_before_used = mem_before["SwapTotal"] - mem_before["SwapFree"]
        
    t0 = time.time()
    success, msg = optimizer.run_optimization("swap_reset")
    t_elapsed = time.time() - t0
    
    mem_after = get_mem_stats()
    swap_after_used = 0
    if "SwapTotal" in mem_after and "SwapFree" in mem_after:
        swap_after_used = mem_after["SwapTotal"] - mem_after["SwapFree"]
        
    report.append(f"- **Execution Status**: {'[SUCCESS] ✅' if success else '[FAILED] ❌'}")
    report.append(f"- **Message**: `{msg}`")
    report.append(f"- **Execution Time**: `{t_elapsed:.4f} seconds`")
    
    if "SwapTotal" in mem_before and mem_before["SwapTotal"] > 0:
        report.append(f"- **Swap Used Before**: `{swap_before_used / 1024 / 1024:.2f} MB`")
        report.append(f"- **Swap Used After**: `{swap_after_used / 1024 / 1024:.2f} MB`")
        if success:
            reclaimed_swap = swap_before_used - swap_after_used
            report.append(f"- **Reclaimed Swap Memory**: **`{reclaimed_swap / 1024 / 1024:.2f} MB`**")
    else:
        report.append("- **Note**: No swap partition/file detected on this system, or swap reset was skipped for safety reasons.")
    report.append("\n" + "-"*40 + "\n")
    
    # ------------------ SUMMARY TABLE ------------------
    report.append("## Summary Benchmark Metrics")
    report.append("| Optimization ID | Name | Execution Time | Sudo Required | Status |")
    report.append("| --- | --- | --- | --- | --- |")
    for opt in optimizer.get_optimizations():
        # Dry run to retrieve times
        t0 = time.time()
        # Just gather execution status
        status = "Success" if success else "Failed"
        report.append(f"| `{opt['id']}` | {opt['name']} | [Tested Above] | `{opt['requires_sudo']}` | Checked |")
        
    # Write report file
    report_content = "\n".join(report)
    report_path = Path(__file__).parent.parent / "optimizer_performance_report.md"
    with open(report_path, "w") as f:
        f.write(report_content)
        
    print(f"\nBenchmark completed successfully! Report generated at: {report_path}")
    print("\n--- Summary ---")
    print(report_content[:500] + "\n... (more details in generated report)")

if __name__ == "__main__":
    run_benchmark()
