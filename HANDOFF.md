<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-02 by `/opt/homebrew/bin/python3.14 -m pytest -q` (581 passed/5 skipped) + `python3 core/statutor_doctor.py .` (clean)
last_worker: antigravity
last_machine: unknown
handoff_id: none
supersedes: none

## Goal
Revision Google Antigravity adapter and harness compatibility as v0.7.0 (T-0044, D-0025).

## Last verified state
Antigravity adapter revisioned to v0.7.0 cleanly:
- `pyproject.toml`, `.claude-plugin/plugin.json`, `adapters/antigravity/plugin.json` bumped to 0.7.0.
- `README.md` updated with Antigravity adapter table row.
- Consumed plan archived to `plans/archive/v0.7-antigravity-adapter.md`.
- `tests/test_release_gate.py` updated to 0.7.0 parity.
- 581 tests passed, 5 skipped; `statutor-doctor .` clean; global hooks and plugin link active.

## Next action
1. Stage modified files (`git add pyproject.toml .claude-plugin/plugin.json adapters/antigravity/ README.md plans/archive/ tests/test_release_gate.py HANDOFF.md`).
2. Verify staged index with `statutor staged .`.
3. Commit v0.7.0 revision.

## Gotchas
Antigravity PreToolUse requires `decision: "allow"` or `decision: "deny"`; Claude Code expects silence on allow. `statutor hook` auto-detects caller schema via `toolCall`/`workspacePaths`. `write_to_file` with `Append: true` is forbidden on `overwrite_bounded` registers.

## Do not touch
Embedded TEMPLATES and INIT_PROFILES; root `.pre-commit-hooks.yaml`; plugin layout; plans/archive.
