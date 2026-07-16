<div align="center">
  <h1>Marmot</h1>
  <p><em>Clean, uninstall, analyze, optimize, and monitor your Debian Linux from the terminal.</em></p>
</div>

<p align="center">
  <a href="https://github.com/aquistus/Marmot/stargazers"><img src="https://img.shields.io/github/stars/aquistus/Marmot?style=flat-square" alt="Stars"></a>
  <a href="https://github.com/aquistus/Marmot/releases"><img src="https://img.shields.io/github/v/tag/aquistus/Marmot?label=version&style=flat-square" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL_v3-blue.svg?style=flat-square" alt="License"></a>
  <a href="https://www.debian.org/"><img src="https://img.shields.io/badge/platform-Debian_Linux-red?style=flat-square&logo=Debian" alt="Debian"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/language-Python_3.13-blue?style=flat-square&logo=Python" alt="Python"></a>
  <a href="https://github.com/Textualize/textual"><img src="https://img.shields.io/badge/framework-Textual-green?style=flat-square" alt="Textual"></a>
</p>

<p align="center">
  <img src="https://images.unsplash.com/photo-1472457897821-70d3819a0e24?auto=format&fit=crop&w=1000&q=80" alt="Marmot TUI System Cleaner" width="1000" />
</p>

> **Marmot** is a premium, Linux-native alternative to Mac system utilities, specifically customized for **Debian-based systems**. It runs entirely as a regular user, dynamically escalating privileges via **Polkit (`pkexec`)** only when administrative actions are triggered.

## Features

- **All-in-One Linux Toolkit**: Replaces system monitors, `ncdu`, `apt-get clean`, `journalctl`, and custom scanning scripts in a single TUI interface.
- **Bento System Monitor**: Real-time CPU usage/temperature, RAM, Swap allocation, Network bandwidth, and Disk volume states.
- **Deep Cleaner**: Safely vacuums user caches (`~/.cache`), system trash, apt cache archives, systemd logs, and developer build files (`node_modules`, `.venv`, etc.).
- **Smart Package Uninstaller**: Searches Debian packages, queries active configuration/remnant files in user directories, and purges them safely.
- **Disk Usage Analyzer**: Interactive tree explorer (an alternative to `ncdu`) allowing you to recursively navigate folders and inspect sizes asynchronously.
- **System Optimizer**: One-click actions to sync & drop RAM page cache, flush DNS resolvers, reset failed systemd services, and cycle swap space safely.

## Quick Start

**Ensure Python 3.13 & pip are installed**

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
```

**Clone and Setup**

```bash
git clone https://github.com/aquistus/Marmot.git ~/Marmot
cd ~/Marmot
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install textual rich
```

**Run**

```bash
./marmot
```

### Keyboard Navigation & Controls

- `TAB` / `Shift+TAB` : Switch between active Tabs (`Monitor`, `Cleaner`, `Uninstaller`, `Disk Analyzer`, `Optimizer`)
- `Arrow Keys` / `h/j/k/l` : Navigate through lists, checkbox options, and directories
- `Enter` : Select, toggle checkboxes, trigger scan/action buttons
- `q` : Quit Marmot

## Security & Safety Design

Marmot is designed from the ground up for Debian's strict security model:

1. **Regular User Execution**: The entire TUI runs as a non-privileged user. It does not run as `root` or require `sudo ./marmot`, protecting the system from interface-level vulnerabilities.
2. **Polkit Integration (`pkexec`)**: When administrative actions (like RAM dropping or APT cleaning) are executed, Marmot invokes `pkexec` to securely prompt the user for password authentication.
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
