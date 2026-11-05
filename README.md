<div align="center">
  <h1>Marmot</h1>
  <p><em>Clean, uninstall, analyze, optimize, and monitor your Linux (Debian / Arch based) from the terminal.</em></p>
</div>

<p align="center">
  <a href="https://github.com/aquistusfami/Marmot/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/aquistusfami/Marmot/ci.yml?branch=main&style=flat-square&label=CI" alt="CI"></a>
  <a href="https://github.com/aquistusfami/Marmot/stargazers"><img src="https://img.shields.io/github/stars/aquistusfami/Marmot?style=flat-square" alt="Stars"></a>
  <a href="https://github.com/aquistusfami/Marmot/releases"><img src="https://img.shields.io/github/v/tag/aquistusfami/Marmot?label=version&style=flat-square" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL_v3-blue.svg?style=flat-square" alt="License"></a>
  <a href="https://www.debian.org/"><img src="https://img.shields.io/badge/platform-Debian_Linux-red?style=flat-square&logo=Debian" alt="Debian"></a>
  <a href="https://archlinux.org/"><img src="https://img.shields.io/badge/platform-Arch_Linux-1793d1?style=flat-square&logo=Arch-Linux" alt="Arch"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/language-Python_3.10+-blue?style=flat-square&logo=Python" alt="Python"></a>
  <a href="https://github.com/Textualize/textual"><img src="https://img.shields.io/badge/framework-Textual-green?style=flat-square" alt="Textual"></a>
</p>

<p align="center">
  <img src="https://images.unsplash.com/photo-1472457897821-70d3819a0e24?auto=format&fit=crop&w=1000&q=80" alt="Marmot TUI System Cleaner" width="1000" />
</p>

> **Marmot** is a premium, Linux-native alternative to Mac system utilities, built for **Debian-based (apt) and Arch-based (pacman) systems**. It runs entirely as a regular user, dynamically escalating privileges via **Polkit (`pkexec`)** only when administrative actions are triggered.

## Features

- **All-in-One Linux Toolkit**: Replaces system monitors, `ncdu`, `apt-get clean` / `paccache`, `journalctl`, and custom scanning scripts in a single TUI interface.
- **Bento System Monitor**: Real-time CPU usage/temperature, RAM, Swap allocation, Network bandwidth, and Disk volume states.
- **Deep Cleaner**: Safely vacuums user caches (`~/.cache`), system trash, apt or pacman package caches, systemd logs, and developer build files (`node_modules`, `.venv`, etc.).
- **Smart Package Uninstaller**: Searches apt or pacman packages, previews every package the removal will take with it, and lets you tick which leftover config/cache folders (exact name match) to delete.
- **Disk Usage Analyzer**: Interactive tree explorer (an alternative to `ncdu`) allowing you to recursively navigate folders and inspect sizes asynchronously.
- **System Optimizer**: One-click actions to sync & drop RAM page cache, flush DNS resolvers, reset failed systemd services, and cycle swap space safely.

## Quick Start

**Requirements:** Python 3.10+, polkit (`pkexec`) for privileged actions. On Arch, `pacman-contrib` provides `paccache` for the package-cache cleaner.

**Install** with [uv](https://docs.astral.sh/uv/) (or `pipx install git+https://github.com/aquistusfami/Marmot`):

```bash
uv tool install git+https://github.com/aquistusfami/Marmot
marmot
```

Upgrade with `uv tool upgrade marmot-tui`, remove with `uv tool uninstall marmot-tui`.

**Supported distributions**

| Family | Package backend |
|---|---|
| Debian, Ubuntu, Mint, Pop!_OS, Kali | apt / dpkg |
| Arch, Manjaro, EndeavourOS, CachyOS | pacman |
| Fedora, RHEL, Rocky, Alma | dnf (dnf4 and dnf5) |
| openSUSE Tumbleweed / Leap | zypper |
| Alpine | apk |
| any distro | Flatpak apps (uninstall, unused runtimes) |

Docker/Podman and Snap cleanup appear automatically when those tools are installed.

Journal cleaning and service reset need systemd.

### Command line

Every cleaning action also works without the TUI (scripts, cron, SSH):

```bash
marmot status [--json]                    # CPU, RAM, disks, battery
marmot scan [--json]                      # what can be cleaned, with item ids
marmot clean user_cache dev_junk --dry-run
marmot clean user_cache --keep-cache mozilla yay --yes
marmot undo                               # restore what the last action moved to Trash
marmot history
```

### Keyboard Navigation & Controls

- `TAB` / `Shift+TAB` : Switch between active Tabs (`Monitor`, `Cleaner`, `Uninstaller`, `Disk Analyzer`, `Optimizer`)
- `Arrow Keys` / `h/j/k/l` : Navigate through lists, checkbox options, and directories
- `Enter` : Select, toggle checkboxes, trigger scan/action buttons
- `q` : Quit Marmot

## Development

```bash
git clone https://github.com/aquistusfami/Marmot.git && cd Marmot
uv run marmot            # run from source
uv run pytest            # tests (incl. a headless TUI smoke test)
uv run ruff check        # lint
```

CI runs lint, tests on Python 3.10–3.14, tests inside an Arch Linux container, and builds the wheel. Pushing a tag `vX.Y.Z` that matches `src/marmot/__init__.py` publishes a GitHub release. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security & Safety Design

Marmot is designed around a least-privilege security model:

1. **Regular User Execution**: The entire TUI runs as a non-privileged user. It does not run as `root` or require `sudo ./marmot`, protecting the system from interface-level vulnerabilities.
2. **Polkit Integration (`pkexec`)**: When administrative actions (like RAM dropping or package cache cleaning) are executed, Marmot invokes `pkexec` to securely prompt the user for password authentication.
3. **Dirty RAM Syncing**: Before purging RAM caches, Marmot runs `sync` to flush all pending filesystem changes, guaranteeing zero data loss.
4. **Swap Reset Safety**: Before cycling swap memory, Marmot verifies that `free RAM > active swap` to prevent Out-Of-Memory (OOM) lockups.

## Features in Detail

### Real-Time Bento Monitor
Shows a multi-card dashboard updating system statistics on a 1-second interval:
```text
┌── CPU STATUS ─────────────────────────┐  ┌── MEMORY STATUS ──────────────────────┐
│ Usage: 8.4%                           │  │ RAM: 4.82 GB / 15.60 GB (30.9%)       │
│ [████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  │  │ [██████████░░░░░░░░░░░░░░░░░░░░░░░░]  │
│ Temp: 42°C                            │  │ Swap: 0 MB / 2.00 GB (0.0%)           │
└───────────────────────────────────────┘  └───────────────────────────────────────┘
```

### Deep System Cleaner
Scans and checks items safely before removing them:
```text
Select areas to clean:
[x] User Caches (~/.cache)                     (4.82 GB)
[x] System Trash Bin                           (1.20 GB)
[ ] APT Package Archives                       (0 B)
[ ] Systemd Logs (keep last 3 days)            (120.4 MB)
[ ] Developer Junk (node_modules, target, venv) (15.42 GB)
```

### Smart App Uninstaller
Search installed packages and purges configuration remnants:
```text
Search installed packages:
[ curl                               ]
  * curl (7.88.1-10+deb12u5)
  * libcurl4 (7.88.1-10+deb12u5)
---------------------------------------
Remnant config files found in:
~/.config/curl/
~/.cache/curl/
```
