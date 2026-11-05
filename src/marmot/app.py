"""Marmot TUI. Every slow or privileged action runs in a worker thread so the UI never freezes."""
import platform
from collections import deque
from pathlib import Path

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    SelectionList,
    Sparkline,
    Static,
    TabbedContent,
    TabPane,
)
from textual.worker import get_current_worker

from marmot import trash
from marmot.analyzer import DiskAnalyzer, ScanCancelled
from marmot.cleaner import SystemCleaner
from marmot.monitor import SystemMonitor
from marmot.optimizer import SystemOptimizer
from marmot.uninstaller import PackageUninstaller

TABS = [("1", "pane-monitor", "Monitor"), ("2", "pane-cleaner", "Cleaner"), ("3", "pane-uninstaller", "Uninstall"),
        ("4", "pane-analyzer", "Analyze"), ("5", "pane-optimizer", "Optimize")]
SHOWN_PACKAGES = 150


def human(n: float) -> str:
    if n < 0:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def bar(pct: float, width: int = 24) -> str:
    """Coloured text bar: green < 60% < yellow < 85% < red."""
    pct = max(0.0, min(100.0, pct))
    filled = round(pct / 100 * width)
    color = "green" if pct < 60 else "yellow" if pct < 85 else "red"
    return f"[{color}]{'━' * filled}[/][dim]{'━' * (width - filled)}[/]"


def os_name() -> str:
    try:
        return platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
    except OSError:
        return "Linux"


def uptime(s: float) -> str:
    d, rem = divmod(int(s), 86400)
    h, m = divmod(rem // 60, 60)
    return (f"{d}d " if d else "") + f"{h}h {m:02}m"


class Card(Vertical):
    """Bordered panel with a title in the border."""

    def __init__(self, title: str, *children, **kw):
        super().__init__(*children, **kw)
        self.border_title = title


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [("escape", "dismiss(False)", "Cancel"), ("y", "dismiss(True)", "Yes"), ("n", "dismiss(False)", "No")]

    def __init__(self, message: str, confirm: str = "Confirm"):
        super().__init__()
        self.message, self.confirm = message, confirm

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static(self.message, id="confirm-msg")
            with Horizontal(classes="button-row"):
                yield Button(self.confirm, variant="error", id="confirm-yes")
                yield Button("Cancel", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class PackageListItem(ListItem):
    def __init__(self, package_info: dict):
        super().__init__()
        self.package_info = package_info

    def compose(self) -> ComposeResult:
        p = self.package_info
        tag = " [magenta]flatpak[/]" if p.get('source') == 'flatpak' else ""
        yield Label(f"[b]{escape(p['name'])}[/b] [dim]{escape(p['version'])}[/]{tag}")


class DiskListItem(ListItem):
    def __init__(self, item_info: dict):
        super().__init__()
        self.item_info = item_info

    def compose(self) -> ComposeResult:
        info = self.item_info
        pct = info.get('percent', 0)
        name = escape(info['name'])
        if info['is_dir']:
            name = f"[b $accent]{name}/[/]"
        yield Label(f"{bar(pct, 16)} {pct:5.1f}%  {info['size_str']:>10}  {name}")


class AnalyzerList(ListView):
    BINDINGS = [
        Binding("backspace", "app.analyzer_up", "Up"),
        Binding("r", "app.analyzer_rescan", "Rescan"),
        Binding("d", "app.analyzer_trash", "Move to Trash"),
    ]


class MarmotApp(App):
    CSS_PATH = "marmot.tcss"
    TITLE = "Marmot"
    BINDINGS = [Binding(key, f"show_tab('{tab}')", label) for key, tab, label in TABS] + [
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.monitor = SystemMonitor()
        self.cleaner = SystemCleaner()
        self.optimizer = SystemOptimizer()
        self.uninstaller = PackageUninstaller()
        self.analyzer = DiskAnalyzer()

        self.clean_scan_data = {}
        self.all_packages = []
        self.current_packages = []
        self.cpu_history = deque([0.0] * 60, maxlen=60)
        self.net_history = deque([0.0] * 60, maxlen=60)
        pm = self.uninstaller.pm
        self.sub_title = f"{os_name()} · {pm['label'] if pm else 'no package manager'}"

    # ---- layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs-main"):
            with TabPane("Monitor", id="pane-monitor"):
                with Grid(id="monitor-grid"):
                    yield Card("CPU", Static(id="cpu-text"), Sparkline(list(self.cpu_history), id="cpu-spark"))
                    yield Card("Memory", Static(id="mem-text"))
                    yield Card("System", Static(id="sys-text"))
                    yield Card("Network", Static(id="net-text"), Sparkline(list(self.net_history), id="net-spark"))
                    yield Card("Disks", Static(id="disk-text"), id="disk-card")
                    yield Card("Top processes", DataTable(id="proc-table", cursor_type="none", zebra_stripes=True),
                               id="proc-card")

            with TabPane("Cleaner", id="pane-cleaner"):
                with Horizontal():
                    with Vertical(id="clean-left"):
                        yield Card("Areas to clean", SelectionList(id="list-clean-items"), id="clean-items-card")
                        yield Card("Cache folders · untick to keep", SelectionList(id="list-clean-cache"),
                                   id="clean-cache-card")
                        yield Checkbox("Move developer files to Trash (undoable)", value=True, id="chk-use-trash")
                        with Horizontal(classes="button-row"):
                            yield Button("Scan", variant="primary", id="btn-clean-scan")
                            yield Button("Preview", id="btn-clean-preview")
                            yield Button("Clean", variant="error", id="btn-clean-run")
                            yield Button("Undo", id="btn-clean-undo")
                    with Vertical(id="clean-right"):
                        yield Card("Summary", Static("Press [b]Scan[/b] to measure what can be cleaned.",
                                                     id="clean-summary"), id="clean-summary-card")
                        yield Card("Log", RichLog(markup=True, wrap=True, id="clean-log"), classes="log-card")

            with TabPane("Uninstaller", id="pane-uninstaller"):
                with Horizontal():
                    with Vertical(id="un-left"):
                        yield Input(placeholder="Search packages…", id="input-uninstall-search")
                        yield Label("", id="lbl-package-count")
                        yield ListView(id="list-packages")
                    with Vertical(id="un-right"):
                        yield Card("Package", Static("Select a package to see what removing it would do.",
                                                     id="lbl-uninstall-info"), id="un-info-card")
                        yield SelectionList(id="list-uninstall-remnants")
                        yield Button("Uninstall", variant="error", id="btn-uninstall-purge", disabled=True)
                        yield Card("Log", RichLog(markup=True, wrap=True, id="uninstall-log"), classes="log-card")

            with TabPane("Disk Analyzer", id="pane-analyzer"):
                with Horizontal(id="analyzer-toolbar"):
                    yield Static("", id="lbl-analyzer-path")
                    yield Button("Up", id="btn-analyzer-up")
                    yield Button("Rescan", variant="primary", id="btn-analyzer-scan")
                yield AnalyzerList(id="list-analyzer")
                yield Static("[dim]Enter opens a folder. [b]d[/b] moves the highlighted item to Trash (only inside "
                             "your home); Undo in the Cleaner tab or `marmot undo` brings it back.[/]", id="analyzer-hint")

            with TabPane("Optimizer", id="pane-optimizer"):
                with VerticalScroll(id="opt-list"):
                    for t in self.optimizer.get_optimizations():
                        with Horizontal(classes="opt-row"):
                            with Vertical(classes="opt-text"):
                                yield Static(f"[b]{t['name']}[/b]")
                                yield Static(f"[dim]{t['desc']}[/]")
                                yield Static("[dim]checking…[/]", id=f"opt-status-{t['id']}", classes="opt-status")
                            yield Button("Run", id=f"opt-run-{t['id']}", disabled=True,
                                         variant="warning" if t['id'] == "drop_caches" else "primary")
                with Horizontal(classes="button-row"):
                    yield Button("Re-check", id="btn-opt-refresh")
                yield Card("Log", RichLog(markup=True, wrap=True, id="opt-log"), classes="log-card", id="opt-log-card")
        yield Footer()

    def on_mount(self) -> None:
        if "tokyo-night" in self.available_themes:
            self.theme = "tokyo-night"
        self.clean_items = self.query_one("#list-clean-items", SelectionList)
        self.clean_cache = self.query_one("#list-clean-cache", SelectionList)
        self.clean_log = self.query_one("#clean-log", RichLog)
        self.uninstall_search = self.query_one("#input-uninstall-search", Input)
        self.uninstall_list = self.query_one("#list-packages", ListView)
        self.uninstall_info = self.query_one("#lbl-uninstall-info", Static)
        self.uninstall_remnants = self.query_one("#list-uninstall-remnants", SelectionList)
        self.uninstall_btn = self.query_one("#btn-uninstall-purge", Button)
        self.uninstall_log = self.query_one("#uninstall-log", RichLog)
        self.analyzer_list = self.query_one("#list-analyzer", AnalyzerList)
        self.analyzer_path_lbl = self.query_one("#lbl-analyzer-path", Static)
        self.optimize_log = self.query_one("#opt-log", RichLog)
        self.query_one("#clean-cache-card").display = False
        self.uninstall_remnants.display = False
        self.query_one("#proc-table", DataTable).add_columns("PID", "Name", "CPU %", "Memory")

        self.update_monitor_dashboard()
        self.update_processes()
        self.set_interval(1.0, self.update_monitor_dashboard)
        self.set_interval(2.0, self.update_processes)
        self.run_worker(self._load_packages_worker, thread=True, group="packages")
        self.refresh_optimizer_checks()

    def action_show_tab(self, tab: str) -> None:
        self.query_one("#tabs-main", TabbedContent).active = tab

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == "pane-analyzer" and not self.analyzer_list.children:
            self.refresh_analyzer()

    # ---- monitor ----------------------------------------------------------------

    def update_monitor_dashboard(self) -> None:
        cpu = self.monitor.get_cpu_usage()
        temp = self.monitor.get_temperature()
        mem = self.monitor.get_memory_info()
        net = self.monitor.get_network_io()
        bat = self.monitor.get_battery_info()
        disks = self.monitor.get_disk_usage()
        sysinfo = self.monitor.get_system_info()

        self.cpu_history.append(cpu)
        temp_s = f"   [dim]temp[/] {temp:.0f}°C" if temp is not None else ""
        self.query_one("#cpu-text", Static).update(f"[b]{cpu:5.1f}%[/b]{temp_s}\n{bar(cpu)}")
        self.query_one("#cpu-spark", Sparkline).data = list(self.cpu_history)

        swap = (f"\n[dim]Swap[/] {human(mem['swap_used'])} / {human(mem['swap_total'])}\n{bar(mem['swap_percent'])}"
                if mem['swap_total'] else "\n[dim]No swap[/]")
        self.query_one("#mem-text", Static).update(
            f"[dim]RAM[/]  {human(mem['used'])} / {human(mem['total'])}  [b]{mem['percent']:.0f}%[/b]\n"
            f"{bar(mem['percent'])}{swap}")

        load = " ".join(f"{x:.2f}" for x in sysinfo['load'])
        lines = [f"[dim]Uptime[/]  {uptime(sysinfo['uptime_s'])}",
                 f"[dim]Load[/]    {load}  [dim]({sysinfo['cpus']} CPUs)[/]",
                 f"[dim]Kernel[/]  {platform.release()}"]
        if bat.get('present') and bat.get('capacity') is not None:
            power = f" · {bat['power']:.1f} W" if bat.get('power') else ""
            lines.append(f"[dim]Battery[/] {bat['capacity']}% {bat['status']}{power}\n{bar(100 - bat['capacity'])}")
        self.query_one("#sys-text", Static).update("\n".join(lines))

        phys = {k: v for k, v in net.items() if self.monitor.is_physical_iface(k)} or net
        rx = sum(v['rx_speed'] for v in phys.values())
        tx = sum(v['tx_speed'] for v in phys.values())
        self.net_history.append(rx + tx)
        per_if = "\n".join(f"[dim]{escape(k)}[/] ↓{human(v['rx_speed'])}/s ↑{human(v['tx_speed'])}/s"
                           for k, v in phys.items())
        self.query_one("#net-text", Static).update(f"[b]↓ {human(rx)}/s   ↑ {human(tx)}/s[/b]\n{per_if}")
        self.query_one("#net-spark", Sparkline).data = list(self.net_history)

        self.query_one("#disk-text", Static).update("\n".join(
            f"{escape(d['mountpoint']):<14} {bar(d['percent'], 30)} {d['percent']:5.1f}%  "
            f"[dim]{human(d['used'])} / {human(d['total'])} · {escape(d['device'])}[/]" for d in disks)
            or "No disks detected.")

    def update_processes(self) -> None:
        table = self.query_one("#proc-table", DataTable)
        table.clear()
        for p in self.monitor.get_top_processes(8):
            table.add_row(str(p['pid']), escape(p['name']), f"{p['cpu']:.1f}", human(p['mem']))

    # ---- buttons ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "btn-clean-scan":
            self.run_clean_scan()
        elif bid == "btn-clean-run":
            self.run_clean_execution()
        elif bid == "btn-clean-preview":
            self.run_clean_execution(dry_run=True)
        elif bid == "btn-clean-undo":
            self.run_undo()
        elif bid == "btn-uninstall-purge":
            self.run_purge_execution()
        elif bid == "btn-analyzer-scan":
            self.action_analyzer_rescan()
        elif bid == "btn-analyzer-up":
            self.action_analyzer_up()
        elif bid == "btn-opt-refresh":
            self.refresh_optimizer_checks()
        elif bid.startswith("opt-run-"):
            self.run_tweak(bid.removeprefix("opt-run-"))

    # ---- cleaner ------------------------------------------------------------------

    def _set_cleaner_busy(self, busy: bool) -> None:
        for bid in ("btn-clean-scan", "btn-clean-preview", "btn-clean-run", "btn-clean-undo"):
            self.query_one(f"#{bid}", Button).disabled = busy

    def run_clean_scan(self) -> None:
        self._set_cleaner_busy(True)
        self.query_one("#clean-summary", Static).update("[yellow]Scanning…[/]")
        self.run_worker(self._clean_scan_worker, thread=True, exclusive=True, group="cleaner")

    def _clean_scan_worker(self) -> None:
        data = self.cleaner.scan()
        self.call_from_thread(self._show_clean_scan, data)

    def _show_clean_scan(self, data: dict) -> None:
        previously = set(self.clean_items.selected) if self.clean_scan_data else {"user_cache", "trash"}
        self.clean_scan_data = data
        self.clean_items.clear_options()
        self.clean_items.add_options([
            (f"{escape(v['name'])}  [b]{v['size_str']}[/b]" + ("  [dim]root[/]" if v['requires_sudo'] else ""),
             k, k in previously) for k, v in data.items()])
        children = data.get('user_cache', {}).get('children', [])
        self.clean_cache.clear_options()
        self.clean_cache.add_options([(f"{escape(c['name'])}  [dim]{c['size_str']}[/]", c['path'], True)
                                      for c in children[:40]])
        self.query_one("#clean-cache-card").display = bool(children) and "user_cache" in self.clean_items.selected
        self.clean_log.write("[dim]Scan completed.[/]")
        self._update_clean_summary()
        self._set_cleaner_busy(False)

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        if event.selection_list.id in ("list-clean-items", "list-clean-cache") and self.clean_scan_data:
            children = self.clean_scan_data.get('user_cache', {}).get('children', [])
            self.query_one("#clean-cache-card").display = bool(children) and "user_cache" in self.clean_items.selected
            self._update_clean_summary()

    def _update_clean_summary(self) -> None:
        sel = [k for k in self.clean_items.selected if k in self.clean_scan_data]
        total, unknown, root = 0, 0, 0
        for k in sel:
            v = self.clean_scan_data[k]
            if k == 'user_cache' and v.get('children'):
                picked = set(self._clean_args()['selected'])
                total += sum(c['size'] for c in v['children'] if c['path'] in picked)
            elif v['size'] < 0:
                unknown += 1
            else:
                total += v['size']
            root += v['requires_sudo']
        everything = sum(max(v['size'], 0) for v in self.clean_scan_data.values())
        extra = (f"\n[dim]+ {unknown} item(s) of unknown size[/]" if unknown else "") + \
                (f"\n[dim]{root} item(s) will ask for your password[/]" if root else "")
        self.query_one("#clean-summary", Static).update(
            f"Selected [b $success]{human(total)}[/] of {human(everything)} found{extra}")

    def _clean_args(self) -> dict:
        cache = list(self.clean_cache.selected)
        children = self.clean_scan_data.get('user_cache', {}).get('children', [])
        # folders beyond the 40 shown are cleaned only when every shown one is ticked
        if len(children) > 40 and len(cache) == min(40, len(children)):
            cache = [c['path'] for c in children]
        return {'selected': cache, 'use_trash': self.query_one("#chk-use-trash", Checkbox).value}

    def run_clean_execution(self, dry_run: bool = False) -> None:
        if not self.clean_scan_data:
            self.clean_log.write("[yellow]Please scan first.[/]")
            return
        items = [i for i in self.clean_items.selected if i in self.clean_scan_data]
        if not items:
            self.clean_log.write("[yellow]Nothing selected.[/]")
            return
        args = self._clean_args()

        def start(confirmed: bool | None = True) -> None:
            if confirmed:
                self._set_cleaner_busy(True)
                self.run_worker(lambda: self._clean_worker(items, dry_run, args), thread=True, exclusive=True,
                                group="cleaner")

        if dry_run:
            start()
        else:
            names = "\n".join(f"  • {escape(self.clean_scan_data[i]['name'])}" for i in items)
            self.push_screen(ConfirmScreen(f"Clean these items?\n\n{names}", "Clean"), start)

    def _clean_worker(self, items: list, dry_run: bool, args: dict) -> None:
        cleaned_any = False
        for item_id in items:
            name = self.clean_scan_data[item_id]['name']
            self.call_from_thread(self.clean_log.write, f"{'Preview' if dry_run else 'Cleaning'}: {escape(name)}")
            success, msg = self.cleaner.clean(
                item_id, self.clean_scan_data, dry_run=dry_run, use_trash=args['use_trash'],
                selected=args['selected'] if item_id == 'user_cache' else None)
            style = "green" if success else "red"
            self.call_from_thread(self.clean_log.write, f"  [{style}]{'✓' if success else '✗'} {escape(msg)}[/]")
            cleaned_any |= success and not dry_run
        if cleaned_any:
            self.analyzer.invalidate()
            self._clean_scan_worker()  # refresh sizes (still in this worker thread)
        else:
            self.call_from_thread(self._set_cleaner_busy, False)

    def run_undo(self) -> None:
        entry, restored, errors = trash.undo_last()
        if entry is None:
            self.clean_log.write("[yellow]Nothing to undo (only actions that moved files to Trash can be undone).[/]")
            return
        self.clean_log.write(f"[green]↶ Undid '{entry['action']}' from {entry['ts']}: restored {len(restored)} item(s)[/]")
        for e in errors:
            self.clean_log.write(f"[red]✗ {escape(e)}[/]")
        self.analyzer.invalidate()

    # ---- uninstaller ----------------------------------------------------------------

    def _load_packages_worker(self) -> None:
        pkgs = self.uninstaller.list_installed_packages(limit=None)
        self.call_from_thread(self._packages_loaded, pkgs)

    def _packages_loaded(self, pkgs: list) -> None:
        self.all_packages = pkgs
        self.refresh_packages_list(self.uninstall_search.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "input-uninstall-search":
            self.refresh_packages_list(event.value)

    def refresh_packages_list(self, query: str = "") -> None:
        q = query.lower()
        matches = [p for p in self.all_packages
                   if not q or q in p['name'].lower() or q in p['summary'].lower()]
        self.current_packages = matches[:SHOWN_PACKAGES]
        self.uninstall_list.clear()
        self.uninstall_list.extend(PackageListItem(p) for p in self.current_packages)
        more = f" · showing {SHOWN_PACKAGES}, type to narrow" if len(matches) > SHOWN_PACKAGES else ""
        self.query_one("#lbl-package-count", Label).update(
            f"[dim]{len(matches)} of {len(self.all_packages)} packages{more}[/]")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if event.list_view.id == "list-packages" and hasattr(item, "package_info"):
            self._show_package(item.package_info)
        elif event.list_view.id == "list-analyzer" and hasattr(item, "item_info"):
            if item.item_info['is_dir']:
                self.analyzer.set_path(item.item_info['path'])
                self.refresh_analyzer()

    def _show_package(self, pkg: dict) -> None:
        source = pkg.get('source', 'system')
        removal = self.uninstaller.preview_removal(pkg['name'], source)
        if removal is None:
            removal_text = "[b red]Cannot be removed: other packages need it (or the preview failed).[/]"
        else:
            extra = [n for n in removal if n != pkg['name']]
            removal_text = f"[b]Removes {len(removal)} package(s):[/] {escape(', '.join(removal))}"
            if extra:
                removal_text += f"\n[b yellow]⚠ {len(extra)} other package(s) go with it.[/]"

        remnants = self.uninstaller.find_remnants(pkg['name'], source)
        self.uninstall_remnants.clear_options()
        self.uninstall_remnants.add_options([(f"{escape(r['path'])}  [dim]{r['size_str']}[/]", r['path'])
                                             for r in remnants])
        self.uninstall_remnants.display = bool(remnants)
        if source == 'flatpak':
            remnant_text = "App data in ~/.var/app is removed with it."
        elif remnants:
            remnant_text = "[yellow]Leftover folders below: tick the ones to move to Trash.[/]"
        else:
            remnant_text = "[dim]No leftover config/cache folders.[/]"
        self.uninstall_info.update(
            f"[b]{escape(pkg['name'])}[/b]  [dim]{escape(pkg['version'])}[/]\n{escape(pkg['summary'])}\n\n"
            f"{removal_text}\n\n{remnant_text}")
        self.selected_package = pkg['name']
        self.selected_source = source
        self.uninstall_btn.disabled = removal is None

    def run_purge_execution(self) -> None:
        if not hasattr(self, "selected_package"):
            return
        args = (self.selected_package, list(self.uninstall_remnants.selected), self.selected_source)

        def go(confirmed: bool | None) -> None:
            if not confirmed:
                return
            self.uninstall_btn.disabled = True
            self.uninstall_log.write(f"Removing {escape(args[0])}…")
            self.run_worker(lambda: self._purge_worker(*args), thread=True, exclusive=True, group="uninstall")

        self.push_screen(ConfirmScreen(f"Uninstall [b]{escape(args[0])}[/b]?", "Uninstall"), go)

    def _purge_worker(self, package: str, remnants: list, source: str) -> None:
        success, msg = self.uninstaller.uninstall(package, remnants, source)
        if success:
            self._load_packages_worker()
        self.call_from_thread(self._purge_done, success, msg)

    def _purge_done(self, success: bool, msg: str) -> None:
        if success:
            self.uninstall_log.write(f"[green]✓ {escape(msg)}[/]")
            self.uninstall_info.update("Select a package to see what removing it would do.")
            self.uninstall_remnants.clear_options()
            self.uninstall_remnants.display = False
        else:
            self.uninstall_log.write(f"[red]✗ {escape(msg)}[/]")
            self.uninstall_btn.disabled = False

    # ---- optimizer ------------------------------------------------------------------

    def refresh_optimizer_checks(self) -> None:
        self.run_worker(self._optimizer_check_worker, thread=True, exclusive=True, group="optimizer")

    def _optimizer_check_worker(self) -> None:
        for t in self.optimizer.get_optimizations():
            st = self.optimizer.check(t['id'])
            self.call_from_thread(self._show_check, t['id'], st)

    def _show_check(self, task_id: str, st: dict) -> None:
        icon = "[green]●[/]" if st['applicable'] else "[dim]○[/]"
        self.query_one(f"#opt-status-{task_id}", Static).update(f"{icon} {escape(st['status'])}")
        self.query_one(f"#opt-run-{task_id}", Button).disabled = not st['applicable']

    def run_tweak(self, task_id: str) -> None:
        self.query_one(f"#opt-run-{task_id}", Button).disabled = True
        self.optimize_log.write(f"Running {task_id}…")

        def work() -> None:
            ok, msg = self.optimizer.run_optimization(task_id)
            self.call_from_thread(self.optimize_log.write, f"[{'green' if ok else 'red'}]{'✓' if ok else '✗'} "
                                                           f"{escape(msg)}[/]")
            self._optimizer_check_worker()

        self.run_worker(work, thread=True, exclusive=True, group="optimizer")

    # ---- analyzer -------------------------------------------------------------------

    def refresh_analyzer(self) -> None:
        self.analyzer_list.clear()
        self.analyzer_path_lbl.update(f"[b]{escape(str(self.analyzer.current_path))}[/b]  [yellow]scanning…[/]")
        # exclusive=True cancels the previous scan when the user navigates before it finishes
        self.run_worker(self._scan_analyzer_worker, thread=True, exclusive=True, group="analyzer")

    def action_analyzer_rescan(self) -> None:
        self.analyzer.invalidate()
        self.refresh_analyzer()

    def action_analyzer_up(self) -> None:
        parent = self.analyzer.current_path.parent
        if parent != self.analyzer.current_path:
            self.analyzer.set_path(str(parent))
            self.refresh_analyzer()

    def action_analyzer_trash(self) -> None:
        item = self.analyzer_list.highlighted_child
        if not hasattr(item, "item_info"):
            return
        path = Path(item.item_info['path'])
        if Path.home() not in path.parents:
            self.notify("Only files inside your home folder can be moved to Trash here.", severity="warning")
            return
        if path == trash.trash_dir() or trash.trash_dir() in path.parents:
            self.notify("That is the Trash itself: empty it from the Cleaner tab.", severity="warning")
            return

        def go(confirmed: bool | None) -> None:
            if not confirmed:
                return
            try:
                name = trash.move_to_trash(path)
            except OSError as e:
                self.notify(f"Could not move to Trash: {e}", severity="error")
                return
            trash.record("analyze:trash", trashed=[{'name': name, 'path': str(path)}])
            self.notify(f"Moved {path.name} to Trash (marmot undo restores it).")
            self.analyzer.invalidate()
            self.refresh_analyzer()

        self.push_screen(ConfirmScreen(f"Move [b]{escape(str(path))}[/b] ({item.item_info['size_str']}) to Trash?",
                                       "Move to Trash"), go)

    def _scan_analyzer_worker(self) -> None:
        worker = get_current_worker()
        path = self.analyzer.current_path

        def progress(done: int, total: int, name: str) -> None:
            self.call_from_thread(self.analyzer_path_lbl.update,
                                  f"[b]{escape(str(path))}[/b]  [yellow]{done}/{total} {escape(name)}[/]")
        try:
            items = self.analyzer.scan_current(progress=progress, cancelled=lambda: worker.is_cancelled)
        except ScanCancelled:
            return

        def update_ui() -> None:
            self.analyzer_list.clear()
            total = human(sum(i['size'] for i in items))
            self.analyzer_path_lbl.update(f"[b]{escape(str(path))}[/b]  [dim]{len(items)} items · {total}[/]")
            if not items:
                self.analyzer_list.append(ListItem(Label("[dim](empty)[/]")))
            else:
                self.analyzer_list.extend(DiskListItem(it) for it in items)
            if self.query_one("#tabs-main", TabbedContent).active == "pane-analyzer":
                self.analyzer_list.focus()

        if not worker.is_cancelled:
            self.call_from_thread(update_ui)


def main() -> None:
    MarmotApp().run()


if __name__ == "__main__":
    main()
