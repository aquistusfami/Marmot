# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Undo: developer build folders and uninstall remnants go to the freedesktop Trash; `marmot undo` (or the Undo button) restores the last batch. Every action is logged to `~/.local/state/marmot/history.jsonl` (`marmot history`).
- Dry-run for every cleaner item (Preview button, `marmot clean --dry-run`).
- Package backends for dnf (dnf4/dnf5), zypper and apk, plus Flatpak apps in the uninstaller.
- Command line: `marmot status|scan|clean|undo|history`, with `--json` output.
- Cleaner: per-folder `~/.cache` selection, orphaned packages, unused Flatpak runtimes, Docker/Podman unused data, old Snap revisions.
- Disk Analyzer: cached directory sizes (instant back/forward), progress, cancel on navigation, percentage bars, stays on one filesystem.

### Changed
- Scans, cleaning and uninstalling run off the UI thread, so the TUI no longer freezes during a pkexec prompt.

### Fixed
- Operation logs printed raw `[success]` markup instead of colours.
- Journal size was always reported as 0 when `journalctl` printed sizes like `1.2G`.

## [1.1.0]

### Added
- pacman backend (Arch and derivatives), auto-detected next to apt.
- Uninstaller previews every package the removal will take with it; purge is disabled if the preview fails.
- Installable package (`uv tool install` / `pipx`) with a `marmot` command; `src/` layout.
- CI: lint, tests on Python 3.10–3.14 and in an Arch container, wheel build; tag-driven GitHub releases.

### Fixed
- Uninstaller deleted any config dir whose name *contained* the package name (e.g. `git` → `~/.config/gitkraken`). Now exact match, opt-in per folder, and limited to `~/.config`, `~/.local/share`, `~/.cache`.
- Developer-junk cleaner deleted Marmot's own `.venv` and unrelated `build/`/`target/` folders. Now requires a project file next to them and skips the running virtualenv.
- Package cache scan crashed on Python < 3.13 when the cache directory was missing.

### Removed
- `./marmot` bash launcher (replaced by the `marmot` entry point).

## [1.0.0]

- Initial release (Debian only).
