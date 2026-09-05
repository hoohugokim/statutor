<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-09-05 by `python3 -m pytest -q` (496 passed/2 skipped) + worktree staged floor + doctor
last_worker: unknown
last_machine: unknown
handoff_id: none
supersedes: none

## Goal
Finish v0.5 worker-provenance prototype (T-0038..T-0041), then run
multi-model adversarial validation reviews before any release gate.

## Last verified state
Prototype complete and merged to `main`: machine identity plus local
registry/CLI (T-0039), HANDOFF metadata plus doctor diagnostics (T-0040),
capabilities plus reconciliation plus isolated CLI E2E (T-0041), R1–R4
triage fixes, D-0023, version 0.5.0 live on PyPI via trusted publishing.
Full gate green; floor and diff checks clean.

## Next action
Dogfood v0.5 per `notes/v0.5-release-guide.md`: live-binary E2E pin
refresh, then real-home phases on separate approvals.

## Gotchas
PATH `statutor-doctor` is pipx v0.4.0 (stale); use worktree code for v0.5
behavior. Skill baseline facts from v0.4 stand; do not fix incidentally.
`_local/`, `assets/`, `notes/`, and the dogfood PDF are untracked human work.

## Do not touch
Embedded TEMPLATES dict; root `.pre-commit-hooks.yaml`; top-level plugin layout;
plans/archive; existing real-home configuration except separately approved
dogfood operations.
