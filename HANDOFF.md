<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-23 (UTC) by focused tests (501 passed); artifact gate pending
last_worker: codex
last_machine: b2246c70d8b687233d5eb990d22786ac
handoff_id: 2786aadafa23529d530c6145a7325119
supersedes: c7d36125f7fd3765e236d3a4208f58d4

## Goal
Finish the v0.7.5 candidate and follow-up flow audit (D-0030/D-0031).

## Last verified state
- Preserved Cursor and 0.7.4 audit fixes; kernel/Cursor/Stop: 340 passed.
- Explicit machine/worker roots survive either argument position; retries
  report already completed. Worker: 86 passed; v0.7.4 registry reader passes.
- CLI payload/help errors, fresh-scaffold and global recovery guidance fixed.
  Setup diagnostics: 72 passed; independent subprocess probes pass.
- Unicode 16 grammar unchanged; pinned conformance: 3 passed on Python 3.15.
  CI adds 3.15. Embedded templates/init profiles remain unchanged.

## Next action
Run the complete artifact gate and independent review, then publish the
reviewable branch. Human tag/registry publication remains separate.

## Gotchas
- Cursor Stop requests one native follow-up at loop 0; later loops stay quiet.
  Native Cursor host consumption remains untested.
- Hooks fail open; staged fails closed. Git hooks allow --no-verify.
- Python/plugins 0.7.5; npm 0.2.0; crate 0.1.3. No registry publication yet.

## Do not touch
Embedded templates/init profiles; frozen archive; DECISIONS.md header;
root pre-commit metadata. Preserve untracked .agents/, _local/, assets/,
notes/, and plans/v0.4-dogfood.pdf.
