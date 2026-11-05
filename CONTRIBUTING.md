# Contributing

1. Install [uv](https://docs.astral.sh/uv/), then `uv run marmot` to run from source.
2. Before opening a PR: `uv run ruff check` and `uv run pytest` must pass (CI runs the same).
3. Anything that deletes files or runs a privileged command needs a test that proves it cannot touch paths outside its scope.
4. New distro support goes in `src/marmot/pkgmgr.py` as a new backend entry, with parser tests in `tests/test_pkgmgr.py`.
5. Add a line under `## [Unreleased]` in `CHANGELOG.md`.

## Releasing

Bump `__version__` in `src/marmot/__init__.py`, move the `Unreleased` notes to a new version heading, merge to `main`, then:

```bash
git tag vX.Y.Z && git push origin vX.Y.Z
```

The release workflow checks the tag matches the version, runs the tests and publishes the wheel and sdist to GitHub Releases.
