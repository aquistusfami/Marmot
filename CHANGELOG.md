# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/).

## [Unreleased]

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
