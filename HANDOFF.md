<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-09-16 by `pytest -q` (498 passed/2 skipped) + staged floor clean + doctor stale-warn only
last_worker: unknown
last_machine: unknown
handoff_id: none
supersedes: none

## Goal
Implement four sure-win assimilations from the Fowler agentic-data reference
report, then resume v0.5 dogfood.

## Last verified state
Tests green; ledger clean. Fowler report completed and saved to
`notes/fowler-making-data-ready-for-agentic-ai-reference.md` (ungoverned).
Sure-win analysis complete: four low-cost items identified, zero code changes
needed. v0.5.0 remains live on PyPI.

## Next action
Implement the four sure wins (AGENTS.md Pitfalls additions):
1. "Gold-only reads" — agents read certified planes, never raw notes/
2. "Retrieved text never gates" — heredoc/shell prose never bypasses validation
3. Name reversibility hierarchy — document the policy ordering principle
4. Verify worker trace retention meets ≥6mo (document, no code change)
Then resume v0.5 dogfood per `notes/v0.5-release-guide.md`.

## Gotchas
PATH `statutor-doctor` is pipx v0.4.0 (stale); use worktree code. The Fowler
report and this analysis live in `notes/` (untracked, ungoverned). Skill
baseline facts from v0.4 stand; do not fix incidentally. `_local/`, `assets/`,
and `plans/v0.4-dogfood.pdf` are untracked human work.

## Do not touch
Embedded TEMPLATES dict; root `.pre-commit-hooks.yaml`; top-level plugin layout;
plans/archive; existing real-home configuration except separately approved
dogfood operations.
