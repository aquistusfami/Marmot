"""Command line entry point: `marmot` opens the TUI, subcommands work headless (scripts, cron, SSH)."""
import argparse
import json
import sys
import time

from marmot import __version__, trash


def _fmt(n: int) -> str:
    if n < 0:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024
    return ""


def cmd_status(args) -> int:
    from marmot.monitor import SystemMonitor
    mon = SystemMonitor()
    mon.get_cpu_usage()  # first sample primes the counters
    time.sleep(0.3)
    data = {"cpu_percent": round(mon.get_cpu_usage(), 1), "temperature_c": mon.get_temperature(),
            "memory": mon.get_memory_info(), "disks": mon.get_disk_usage(), "battery": mon.get_battery_info()}
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    m = data["memory"]
    temp = f"  {data['temperature_c']:.0f}°C" if data["temperature_c"] else ""
    print(f"CPU   {data['cpu_percent']:5.1f}%{temp}")
    print(f"RAM   {m['percent']:5.1f}%  {_fmt(m['used'])} / {_fmt(m['total'])}   swap {_fmt(m['swap_used'])}")
    for d in data["disks"]:
        print(f"Disk  {d['percent']:5.1f}%  {_fmt(d['used'])} / {_fmt(d['total'])}  {d['mountpoint']}")
    b = data["battery"]
    if b.get("present"):
        print(f"Bat   {b['capacity']}%  {b['status']}")
    return 0


def _scan():
    from marmot.cleaner import SystemCleaner
    cleaner = SystemCleaner()
    return cleaner, cleaner.scan()


def cmd_scan(args) -> int:
    _, data = _scan()
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    width = max(len(k) for k in data)
    for key, v in data.items():
        root = "  (root)" if v["requires_sudo"] else ""
        print(f"{key:<{width}}  {v['size_str']:>10}  {v['name']}{root}")
    print("\nClean with: marmot clean <id>... [--dry-run]")
    return 0


def cmd_clean(args) -> int:
    cleaner, data = _scan()
    unknown = [i for i in args.items if i not in data]
    if unknown:
        print(f"Unknown or unavailable item(s): {', '.join(unknown)}. Available: {', '.join(data)}", file=sys.stderr)
        return 2

    selected = None
    if args.keep_cache:
        selected = [c["path"] for c in data["user_cache"].get("children", []) if c["name"] not in args.keep_cache]

    if not args.dry_run and not args.yes:
        if not sys.stdin.isatty():
            print("Refusing to clean without --yes when not interactive (use --dry-run to preview).", file=sys.stderr)
            return 2
        for i in args.items:
            print(f"  {data[i]['name']}: {data[i]['size_str']}")
        if input("Clean these? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 1

    rc = 0
    for item_id in args.items:
        ok, msg = cleaner.clean(item_id, data, dry_run=args.dry_run, use_trash=not args.permanent,
                                selected=selected if item_id == "user_cache" else None)
        print(f"{'✓' if ok else '✗'} {msg}")
        rc |= not ok
    return rc


def cmd_undo(args) -> int:
    entry, restored, errors = trash.undo_last()
    if entry is None:
        print("Nothing to undo (only actions that moved files to Trash can be undone).")
        return 1
    print(f"Undid '{entry['action']}' from {entry['ts']}:")
    for p in restored:
        print(f"  ↶ {p}")
    for e in errors:
        print(f"  ✗ {e}", file=sys.stderr)
    return 1 if errors else 0


def cmd_history(args) -> int:
    for e in trash.load_history()[-args.n:]:
        extra = f"  trashed {len(e['trashed'])}" if e["trashed"] else ""
        freed = f"  freed {_fmt(e['freed'])}" if e.get("freed") else ""
        print(f"{e['ts']}  {e['action']:<20}{freed}{extra}  {e.get('detail', '')}".rstrip())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="marmot", description="Run without a command to open the TUI.")
    p.add_argument("--version", action="version", version=f"marmot {__version__}")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("status", help="CPU, memory, disks, battery")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("scan", help="measure what can be cleaned")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("clean", help="clean items listed by `marmot scan`")
    s.add_argument("items", nargs="+", metavar="ID")
    s.add_argument("-n", "--dry-run", action="store_true", help="only show what would happen")
    s.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    s.add_argument("--permanent", action="store_true", help="delete developer files instead of moving them to Trash")
    s.add_argument("--keep-cache", nargs="+", metavar="NAME", default=[], help="~/.cache folders to keep")
    s.set_defaults(func=cmd_clean)

    s = sub.add_parser("undo", help="restore what the last clean/uninstall moved to Trash")
    s.set_defaults(func=cmd_undo)

    s = sub.add_parser("history", help="show recent actions")
    s.add_argument("-n", type=int, default=20)
    s.set_defaults(func=cmd_history)
    return p


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        from marmot.app import MarmotApp  # textual is only imported for the TUI
        MarmotApp().run()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
