<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-02 by `statutor version` (statutor 0.7.1) + `/opt/homebrew/bin/python3.14 -m pytest -q` (582 passed/5 skipped) + `statutor-doctor .` (clean)
last_worker: antigravity
last_machine: unknown
handoff_id: none
supersedes: none

## Goal
Implement `statutor version` command and release as v0.7.1 (T-0045).

## Last verified state
`statutor version` CLI implemented & tested (582 passed, 5 skipped):
- `core/statutor_core.py`: added `__version__ = "0.7.1"`, handles `statutor version` / `--version` / `-v`.
- `pyproject.toml`, `.claude-plugin/plugin.json`, `adapters/antigravity/plugin.json` bumped to 0.7.1.
- `tests/test_kernel.py`: added `test_version_cli`.
- `tests/test_release_gate.py`: updated for 0.7.1 parity.
- `TASKS.md`: closed T-0045.
- pipx editable install upgraded to 0.7.1; live `statutor version` outputs `statutor 0.7.1`.

## Next action
1. Stage modified files (`git add pyproject.toml .claude-plugin/plugin.json adapters/antigravity/plugin.json core/statutor_core.py tests/ TASKS.md HANDOFF.md`).
2. Verify staged index with `statutor staged .`.
3. Commit v0.7.1 release.

## Gotchas
`statutor version` checks `importlib.metadata.version('statutor')` first, falling back to kernel `__version__` if uninstalled/in development.

## Do not touch
Embedded TEMPLATES and INIT_PROFILES; root `.pre-commit-hooks.yaml`; plugin layout; plans/archive.
