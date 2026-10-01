<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-01 by `pytest -q` (581 passed/5 skipped) + `python3 core/statutor_doctor.py .` (clean)
last_worker: antigravity
last_machine: unknown
handoff_id: none
supersedes: none

## Goal
Implement Google Antigravity adapter and harness compatibility (T-0044, D-0025).

## Last verified state
Antigravity adapter and kernel compatibility implemented & tested (581 passed, 5 skipped):
- `core/statutor_core.py`: tool & arg normalization (run_command, write_to_file, replace_file_content), fail-open PreToolUse & Stop hook auto-detection.
- `core/statutor_worker.py`: registered antigravity & gemini in HARNESSES & CAPABILITIES.
- `adapters/antigravity/`: plugin.json, hooks.json, rules/AGENTS.md, 5 skills (statutor, statutor-init, statutor-doctor, handoff, decide), README.md.
- `tests/test_adapter_antigravity.py`: 17 focused unit/integration tests.
- DECISIONS.md appended D-0025, TASKS.md updated with T-0044.

## Next action
1. Run `python3 core/statutor_doctor.py .` to ensure ledger health is clean.
2. Review git diff for all new files and staged changes.
3. Commit and present summary to user.

## Gotchas
Antigravity PreToolUse requires `decision: "allow"` or `decision: "deny"`; Claude Code expects silence on allow. `statutor hook` auto-detects caller schema via `toolCall`/`workspacePaths`. `write_to_file` with `Append: true` is forbidden on `overwrite_bounded` registers.

## Do not touch
Embedded TEMPLATES and INIT_PROFILES; root `.pre-commit-hooks.yaml`; plugin layout; plans/archive.
