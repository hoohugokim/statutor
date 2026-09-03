<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-09-03 by `python3 -m pytest -q` (488 passed/2 skipped) + worktree staged floor
last_worker: unknown
last_machine: unknown
handoff_id: none
supersedes: none

## Goal
Finish v0.5 worker-provenance prototype (T-0038..T-0041), then run
multi-model adversarial validation reviews before any release gate.

## Last verified state
Prototype complete on `work/v0.5-worker-provenance`: machine identity plus
local registry/CLI (T-0039), HANDOFF metadata plus doctor diagnostics
(T-0040), capabilities plus reconciliation plus isolated CLI E2E (T-0041).
Full gate green; floor and diff checks clean. No real-home mutation,
tag, push, or publish performed.

## Next action
Commit the prototype, then review per `notes/v0.5-adversarial-review.md`.
Triage findings into TASKS before version bump or release gate.

## Gotchas
PATH `statutor-doctor` is pipx v0.4.0 (stale); use worktree code for v0.5
behavior. Skill baseline facts from v0.4 stand; do not fix incidentally.
`_local/`, `assets/`, `notes/`, and the dogfood PDF are untracked human work.

## Do not touch
Embedded TEMPLATES dict; root `.pre-commit-hooks.yaml`; top-level plugin layout;
plans/archive; existing real-home configuration except separately approved
dogfood operations.
