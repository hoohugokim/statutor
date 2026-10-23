<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-23 (UTC) by full artifact gate at 81f9d3f (853 passed, zero skips; Rust 7), independent Standards/Spec review
last_worker: codex
last_machine: b2246c70d8b687233d5eb990d22786ac
handoff_id: 2786aadafa23529d530c6145a7325119
supersedes: c7d36125f7fd3765e236d3a4208f58d4

## Goal
Finish the v0.7.5 candidate and follow-up flow audit (D-0030/D-0031).

## Last verified state
- Preserved Cursor and 0.7.4 kernel/Rust audit fixes (D-0030).
- Explicit roots work in both CLI positions; completion retry guidance is
  accurate without changing schema 1; v0.7.4 registry reader/writer passes.
- Check input/help, fresh-scaffold/global guidance, Cursor Stop/install,
  and absolute Antigravity target scoping fixed; independent probes pass.
- Unicode 16 grammar and embedded templates unchanged; CI adds Python 3.15.
- All package audits, builds, installed-wheel smoke, and ledger checks pass.

## Next action
Review codex/flow-audit-075, then tag/publish v0.7.5 and crate 0.1.3.
npm remains 0.2.0. Registry publication remains a human step.

## Gotchas
- Cursor Stop requests one native follow-up at loop 0; later loops stay quiet.
  Native Cursor host consumption remains untested.
- Hooks fail open; staged fails closed. Git hooks allow --no-verify.
- Python/plugins 0.7.5; npm 0.2.0; crate 0.1.3. No registry publication yet.

## Do not touch
Embedded templates/init profiles; frozen archive; DECISIONS.md header;
root pre-commit metadata. Preserve untracked .agents/, _local/, assets/,
notes/, and plans/v0.4-dogfood.pdf.
