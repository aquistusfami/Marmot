import os
import sys
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Grid, Vertical, Horizontal, ScrollableContainer, Container
from textual.widgets import Header, Footer, TabbedContent, TabPane, Label, ProgressBar, Button, Checkbox, Input, ListView, ListItem, RichLog
from textual.reactive import reactive

# Import Marmot Modules
from modules.monitor import SystemMonitor
from modules.cleaner import SystemCleaner
from modules.optimizer import SystemOptimizer
from modules.uninstaller import PackageUninstaller
from modules.analyzer import DiskAnalyzer


class CPUCard(Container):
    DEFAULT_CLASSES = "bento-card"

    def compose(self) -> ComposeResult:
        yield Label("CPU STATUS", classes="card-title")
        self.usage_label = Label("Usage: Calculating...")
        yield self.usage_label
        self.progress = ProgressBar(total=100, show_percentage=False, show_eta=False)
        yield self.progress
        self.temp_label = Label("Temp: --")
        yield self.temp_label

    def update_stats(self, usage: float, temp: float | None):
        self.usage_label.update(f"Usage: {usage:.1f}%")
        self.progress.update(progress=int(usage))
        if temp is not None:
            self.temp_label.update(f"Temp: {temp:.1f}°C")
        else:
            self.temp_label.update("Temp: N/A")


class MemoryCard(Container):
    DEFAULT_CLASSES = "bento-card"

    def compose(self) -> ComposeResult:
        yield Label("MEMORY STATUS", classes="card-title")
        self.ram_label = Label("RAM: Calculating...")
        yield self.ram_label
        self.ram_progress = ProgressBar(total=100, show_percentage=False, show_eta=False)
        yield self.ram_progress
        self.swap_label = Label("Swap: Calculating...")
        yield self.swap_label
        self.swap_progress = ProgressBar(total=100, show_percentage=False, show_eta=False)
        yield self.swap_progress

    def update_stats(self, mem_info: dict):
        total_gb = mem_info['total'] / (1024**3)
        used_gb = mem_info['used'] / (1024**3)
        self.ram_label.update(f"RAM: {used_gb:.2f} GB / {total_gb:.2f} GB ({mem_info['percent']:.1f}%)")
        self.ram_progress.update(progress=int(mem_info['percent']))
        
        swap_total_gb = mem_info['swap_total'] / (1024**3)
        swap_used_gb = mem_info['swap_used'] / (1024**3)
        self.swap_label.update(f"Swap: {swap_used_gb:.2f} GB / {swap_total_gb:.2f} GB ({mem_info['swap_percent']:.1f}%)")
        self.swap_progress.update(progress=int(mem_info['swap_percent']))


class NetworkCard(Container):
    DEFAULT_CLASSES = "bento-card"

    def compose(self) -> ComposeResult:
        yield Label("NETWORK BANDWIDTH", classes="card-title")
        self.net_label = Label("Calculating network statistics...")
        yield self.net_label

    def update_stats(self, net_info: dict):
        if not net_info:
            self.net_label.update("No active network interfaces found.")
            return
            
        lines = []
        for iface, data in net_info.items():
            rx_speed = data['rx_speed'] / 1024.0 # KB/s
            tx_speed = data['tx_speed'] / 1024.0 # KB/s
            rx_total = data['rx_total'] / (1024**2) # MB
            tx_total = data['tx_total'] / (1024**2) # MB
            
            rx_str = f"{rx_speed:.1f} KB/s" if rx_speed < 1024 else f"{rx_speed/1024:.2f} MB/s"
            tx_str = f"{tx_speed:.1f} KB/s" if tx_speed < 1024 else f"{tx_speed/1024:.2f} MB/s"
            
            lines.append(f"[bold]{iface}:[/bold] Down: [cyan]{rx_str}[/] ([dim]{rx_total:.0f} MB[/]) | Up: [magenta]{tx_str}[/] ([dim]{tx_total:.0f} MB[/])")
            
        self.net_label.update("\n".join(lines))


class BatteryCard(Container):
    DEFAULT_CLASSES = "bento-card"

    def compose(self) -> ComposeResult:
        yield Label("BATTERY STATUS", classes="card-title")
        self.cap_label = Label("Battery: Checking...")
        yield self.cap_label
        self.progress = ProgressBar(total=100, show_percentage=False, show_eta=False)
        yield self.progress
        self.status_label = Label("Status: --")
        yield self.status_label

    def update_stats(self, bat_info: dict):
        if not bat_info['present'] or bat_info['capacity'] is None:
            self.cap_label.update("Battery: Not detected / Desktop power")
            self.progress.update(progress=0)
            self.status_label.update("Status: AC Power Connection")
            return
            
        cap = bat_info['capacity']
        self.cap_label.update(f"Battery Capacity: {cap}%")
        self.progress.update(progress=cap)
        
        status = bat_info['status']
        power = bat_info['power']
        power_str = f" ({power:.2f} W)" if power is not None else ""
        self.status_label.update(f"Status: {status}{power_str}")


class DiskCard(Container):
    DEFAULT_CLASSES = "bento-card"

    def compose(self) -> ComposeResult:
        yield Label("DISK VOLUMES", classes="card-title")
        self.disk_label = Label("Calculating storage info...")
        yield self.disk_label

    def update_stats(self, disk_info: list):
        if not disk_info:
            self.disk_label.update("No disks detected.")
            return
            
        lines = []
        for d in disk_info:
            total_gb = d['total'] / (1024**3)
            used_gb = d['used'] / (1024**3)
            
            bar_len = 16
            filled_len = int(bar_len * d['percent'] / 100)
            bar = "█" * filled_len + "░" * (bar_len - filled_len)
            
            lines.append(
                f"[bold]{d['mountpoint']}[/bold] [dim]({d['device']})[/dim]\n"
                f"Used: {used_gb:.1f} GB / {total_gb:.1f} GB ({d['percent']:.1f}%)\n"
                f"[cyan]{bar}[/]"
            )
        self.disk_label.update("\n\n".join(lines))


class PackageListItem(ListItem):
    def __init__(self, package_info: dict):
        super().__init__()
        self.package_info = package_info
        
    def compose(self) -> ComposeResult:
        yield Label(f"[bold cyan]{self.package_info['name']}[/bold cyan] ([dim]{self.package_info['version']}[/dim])\n[dim]{self.package_info['summary']}[/dim]")


class DiskListItem(ListItem):
    def __init__(self, item_info: dict):
        super().__init__()
        self.item_info = item_info
        
    def compose(self) -> ComposeResult:
        prefix = "[DIR] " if self.item_info['is_dir'] else "      "
        name_style = "[bold cyan]" if self.item_info['is_dir'] else "[white]"
        yield Label(f"{prefix}{name_style}{self.item_info['name']}[/] - [magenta]{self.item_info['size_str']}[/]")


class MarmotApp(App):
    CSS_PATH = "marmot.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("tab", "next_tab", "Switch Tab"),
    ]

    def __init__(self):
        super().__init__()
        self.monitor = SystemMonitor()
        self.cleaner = SystemCleaner()
        self.optimizer = SystemOptimizer()
        self.uninstaller = PackageUninstaller()
        self.analyzer = DiskAnalyzer()
        
        # Scan status data caching
        self.clean_scan_data = {}
        self.current_packages = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with TabbedContent(id="tabs-main"):
            # 1. Live Monitor
            with TabPane("Monitor", id="pane-monitor"):
                with Vertical(classes="monitor-container"):
                    with Horizontal(classes="monitor-row"):
                        self.cpu_card = CPUCard()
                        self.mem_card = MemoryCard()
                        yield self.cpu_card
                        yield self.mem_card
                    with Horizontal(classes="monitor-row"):
                        self.net_card = NetworkCard()
                        self.disk_card = DiskCard()
                        self.bat_card = BatteryCard()
                        yield self.net_card
                        yield self.disk_card
                        yield self.bat_card
                    
            # 2. Deep Cleaner
            with TabPane("Cleaner", id="pane-cleaner"):
                with Horizontal():
                    with Vertical(id="cleaner-options-panel", classes="half-width-pad-right"):
                        yield Label("[bold]Select areas to clean:[/bold]\n")
                        yield Checkbox("User Caches (~/.cache)", value=True, id="chk-user-cache")
                        yield Checkbox("System Trash Bin", value=True, id="chk-trash")
                        yield Checkbox("Apt Package Caches (.deb)", value=False, id="chk-apt-cache")
                        yield Checkbox("Systemd Journal Logs", value=False, id="chk-systemd-logs")
                        yield Checkbox("Developer Build Files (node_modules, target...)", value=False, id="chk-dev-junk")
                        
                        with Horizontal(classes="margin-top-2"):
                            yield Button("Scan Storage", variant="primary", id="btn-clean-scan")
                            yield Button("Clean Selected", variant="error", id="btn-clean-run", classes="margin-left-2")
                            
                    with Vertical(classes="half-width"):
                        yield Label("[bold]Operation Logs:[/bold]")
                        self.clean_log = RichLog(highlight=True, classes="log-view")
                        yield self.clean_log
                        
            # 3. Smart Uninstaller
            with TabPane("Uninstaller", id="pane-uninstaller"):
                with Horizontal():
                    with Vertical(classes="forty-width-pad-right"):
                        yield Label("[bold]Search installed packages:[/bold]")
                        self.uninstall_search = Input(placeholder="Type package name...", id="input-uninstall-search")
                        yield self.uninstall_search
                        self.uninstall_list = ListView(id="list-packages")
                        yield self.uninstall_list
                        
                    with Vertical(classes="sixty-width"):
                        yield Label("[bold]Package Information & Remnants:[/bold]")
                        self.uninstall_info = Label("Select a package from the list to view details.", id="lbl-uninstall-info")
                        yield self.uninstall_info
                        self.uninstall_btn = Button("Purge Package & Configuration Remnants", variant="error", id="btn-uninstall-purge", disabled=True)
                        yield self.uninstall_btn
                        yield Label("[bold]Uninstaller Execution Log:[/bold]", classes="margin-top-1")
                        self.uninstall_log = RichLog(highlight=True, classes="log-view")
                        yield self.uninstall_log
                        
            # 4. Disk Analyzer
            with TabPane("Disk Analyzer", id="pane-analyzer"):
                yield Label("[bold]Visual Disk Space Usage (ncdu alternative)[/bold]")
                self.analyzer_path_lbl = Label(f"Current Directory: {self.analyzer.current_path}", id="lbl-analyzer-path")
                yield self.analyzer_path_lbl
                with Horizontal(classes="analyzer-header"):
                    yield Button("Scan Current Directory", variant="primary", id="btn-analyzer-scan")
                    yield Button("Go to Parent (..)", variant="default", id="btn-analyzer-up", classes="margin-left-2")
                self.analyzer_list = ListView(id="list-analyzer")
                yield self.analyzer_list
                
            # 5. System Optimizer
            with TabPane("Optimizer", id="pane-optimizer"):
                with Horizontal():
                    with Vertical(classes="half-width-pad-right"):
                        yield Label("[bold]Available Optimization Tweak Actions:[/bold]\n")
                        with Grid(classes="optimize-grid"):
                            yield Button("Drop RAM Page Cache", id="btn-opt-drop-caches", variant="primary")
                            yield Button("Flush System DNS", id="btn-opt-flush-dns", variant="primary")
                            yield Button("Reset Failed Services", id="btn-opt-reset-services", variant="primary")
                            yield Button("Reclaim Swap Space", id="btn-opt-swap-reset", variant="primary")
                    with Vertical(classes="half-width"):
                        yield Label("[bold]Optimizer Execution Log:[/bold]")
                        self.optimize_log = RichLog(highlight=True, classes="log-view")
                        yield self.optimize_log
                        
        yield Footer()

    def on_mount(self) -> None:
        # Start update timer for monitor dashboard (1-second interval)
        self.set_interval(1.0, self.update_monitor_dashboard)
        
        # Populate initial packages list
        self.refresh_packages_list()
        
        # Trigger initial monitor fetch
        self.update_monitor_dashboard()

    def update_monitor_dashboard(self) -> None:
        # Fetch stats
        cpu = self.monitor.get_cpu_usage()
        temp = self.monitor.get_temperature()
        mem = self.monitor.get_memory_info()
        net = self.monitor.get_network_io()
        bat = self.monitor.get_battery_info()
        disks = self.monitor.get_disk_usage()
        
        # Update widgets
        self.cpu_card.update_stats(cpu, temp)
        self.mem_card.update_stats(mem)
        self.net_card.update_stats(net)
        self.disk_card.update_stats(disks)
        
        if not bat.get("present", False):
            self.bat_card.styles.display = "none"
        else:
            self.bat_card.styles.display = "block"
            self.bat_card.update_stats(bat)

    # --- TAB NAVIGATION ACTION ---
    def action_next_tab(self) -> None:
        tabs = self.query_one("#tabs-main", TabbedContent)
        current = tabs.active
        # Simple cycling
        tab_ids = ["pane-monitor", "pane-cleaner", "pane-uninstaller", "pane-analyzer", "pane-optimizer"]
        try:
            idx = tab_ids.index(current)
            next_idx = (idx + 1) % len(tab_ids)
            tabs.active = tab_ids[next_idx]
        except ValueError:
            pass

    # --- CLEANER TAB LOGIC ---
    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        
        if button_id == "btn-clean-scan":
            self.run_clean_scan()
        elif button_id == "btn-clean-run":
            self.run_clean_execution()
        elif button_id == "btn-opt-drop-caches":
            self.run_tweak("drop_caches")
        elif button_id == "btn-opt-flush-dns":
            self.run_tweak("flush_dns")
        elif button_id == "btn-opt-reset-services":
            self.run_tweak("reset_services")
        elif button_id == "btn-opt-swap-reset":
            self.run_tweak("swap_reset")
        elif button_id == "btn-uninstall-purge":
            self.run_purge_execution()
        elif button_id == "btn-analyzer-scan":
            self.refresh_analyzer()
        elif button_id == "btn-analyzer-up":
            # Navigate to parent
            parent = self.analyzer.current_path.parent
            if parent != self.analyzer.current_path:
                self.analyzer.set_path(str(parent))
                self.analyzer_path_lbl.update(f"Current Directory: {self.analyzer.current_path}")
                self.refresh_analyzer()

    def run_clean_scan(self) -> None:
        self.clean_log.write("Starting storage scan...")
        self.clean_scan_data = self.cleaner.scan()
        self.clean_log.write("Scan completed successfully.\n")
        
        # Display sizes inside checkboxes
        for key, val in self.clean_scan_data.items():
            self.clean_log.write(f"- [bold]{val['name']}[/]: {val['size_str']} ({val['desc']})")
            
            # Update check label with size info dynamically
            if key == 'user_cache':
                self.query_one("#chk-user-cache", Checkbox).label = f"User Caches: {val['size_str']}"
            elif key == 'trash':
                self.query_one("#chk-trash", Checkbox).label = f"System Trash Bin: {val['size_str']}"
            elif key == 'apt_cache':
                self.query_one("#chk-apt-cache", Checkbox).label = f"Apt Package Caches: {val['size_str']}"
            elif key == 'systemd_logs':
                self.query_one("#chk-systemd-logs", Checkbox).label = f"Systemd Journal Logs: {val['size_str']}"
            elif key == 'dev_junk':
                self.query_one("#chk-dev-junk", Checkbox).label = f"Developer Build Files: {val['size_str']}"

    def run_clean_execution(self) -> None:
        if not self.clean_scan_data:
            self.clean_log.write("[warning]Please scan storage first before cleaning.[/]")
            return
            
        chk_mapping = {
            'user_cache': "#chk-user-cache",
            'trash': "#chk-trash",
            'apt_cache': "#chk-apt-cache",
            'systemd_logs': "#chk-systemd-logs",
            'dev_junk': "#chk-dev-junk"
        }
        
        cleaned_any = False
        for item_id, selector in chk_mapping.items():
            chk = self.query_one(selector, Checkbox)
            if chk.value:
                self.clean_log.write(f"Cleaning {self.clean_scan_data[item_id]['name']}...")
                success, msg = self.cleaner.clean(item_id, self.clean_scan_data)
                if success:
                    self.clean_log.write(f"[success]✓ {msg}[/]")
                    cleaned_any = True
                else:
                    self.clean_log.write(f"[danger]✗ {msg}[/]")
                    
        if cleaned_any:
            # Refresh Scan data
            self.run_clean_scan()

    # --- UNINSTALLER TAB LOGIC ---
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "input-uninstall-search":
            self.refresh_packages_list(event.value)

    def refresh_packages_list(self, query: str = "") -> None:
        self.uninstall_list.clear()
        self.current_packages = self.uninstaller.list_installed_packages(query)
        for pkg in self.current_packages:
            self.uninstall_list.append(PackageListItem(pkg))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "list-packages":
            item = event.item
            if item and hasattr(item, "package_info"):
                pkg = item.package_info
                
                # Scan for remnant configs
                remnants = self.uninstaller.find_remnants(pkg['name'])
                remnant_text = ""
                self.selected_remnant_paths = []
                
                if remnants:
                    remnant_text = "\n\n[bold yellow]Remnant directories found:[/] "
                    for r in remnants:
                        self.selected_remnant_paths.append(r['path'])
                        remnant_text += f"\n- {r['path']} ({r['size_str']})"
                else:
                    remnant_text = "\n\nNo config/cache remnants detected."
                    
                info = (
                    f"[bold]{pkg['name']}[/bold]\n"
                    f"Version: {pkg['version']}\n"
                    f"Summary: {pkg['summary']}"
                    f"{remnant_text}"
                )
                self.uninstall_info.update(info)
                self.selected_package = pkg['name']
                self.uninstall_btn.disabled = False
                
        elif event.list_view.id == "list-analyzer":
            item = event.item
            if item and hasattr(item, "item_info"):
                info = item.item_info
                if info['is_dir']:
                    self.analyzer.set_path(info['path'])
                    self.analyzer_path_lbl.update(f"Current Directory: {self.analyzer.current_path}")
                    self.refresh_analyzer()

    def run_purge_execution(self) -> None:
        if not hasattr(self, "selected_package"):
            return
            
        self.uninstall_log.write(f"Executing purge on {self.selected_package}...")
        success, msg = self.uninstaller.uninstall(self.selected_package, getattr(self, "selected_remnant_paths", None))
        
        if success:
            self.uninstall_log.write(f"[success]✓ {msg}[/]")
            self.uninstall_info.update("Select a package from the list to view details.")
            self.uninstall_btn.disabled = True
            # Refresh package list
            self.refresh_packages_list(self.uninstall_search.value)
        else:
            self.uninstall_log.write(f"[danger]✗ {msg}[/]")

    # --- OPTIMIZER TAB LOGIC ---
    def run_tweak(self, tweak_id: str) -> None:
        self.optimize_log.write(f"Running optimization task: {tweak_id}...")
        success, msg = self.optimizer.run_optimization(tweak_id)
        if success:
            self.optimize_log.write(f"[success]✓ {msg}[/]\n")
        else:
            self.optimize_log.write(f"[danger]✗ {msg}[/]\n")

    # --- ANALYZER TAB LOGIC ---
    def refresh_analyzer(self) -> None:
        self.analyzer_list.clear()
        self.analyzer_path_lbl.update(f"Current Directory: [bold]{self.analyzer.current_path}[/bold] [yellow](Scanning...)[/yellow]")
        
        # Insert a visual loading feedback message into the list (wrapped in ListItem so clear() can remove it)
        self.analyzer_list.append(ListItem(Label(" Scanning directory contents, please wait...", classes="analyzer-loading-msg")))
        
        # Offload the blocking filesystem scan to a background thread worker
        self.run_worker(self._scan_analyzer_worker, thread=True, exclusive=True)
        
    def _scan_analyzer_worker(self) -> None:
        # Executes in a background thread to prevent UI freezing
        items = self.analyzer.scan_current()
        
        def update_ui():
            self.analyzer_list.clear()
            self.analyzer_path_lbl.update(f"Current Directory: [bold]{self.analyzer.current_path}[/bold]")
            if not items:
                self.analyzer_list.append(ListItem(Label(" (Empty Directory)", classes="analyzer-loading-label")))
            else:
                for it in items:
                    self.analyzer_list.append(DiskListItem(it))
                    
        # Safely schedule the UI updates back on the main thread
        self.call_from_thread(update_ui)


if __name__ == "__main__":
    app = MarmotApp()
    app.run()
