<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-31 by `fresh cargo → 5 passed; Python↔Rust conformance → 42 passed/2 skipped; full pytest → 297 passed/12 skipped; package audit → 3 passed; doctor + staged clean`

## Goal
Repair v0.3's trust/release gaps, then build the specified v0.4 portable user
layer for global instructions and skills across Claude, Codex, and OpenCode.

## Last verified state
v0.3 shipped; the 2026-08-31 audit found lifecycle, trust, and claim blockers.
D-0015 fixes the trust contract: HEAD/index snapshots, kernel meta-rules, and
exact-tree approval receipts. Package cleanup removed all 83 tracked Cargo
build files (13.4 MB in Git); exact 0.1.1 Cargo/npm payload audits are in CI.
The lifecycle floor now denies record deletion/rename-out and direct frozen
arrival in Python and Rust. Append-only checks raw HEAD/index line identity,
so NUL data or attributes cannot hide rewrites. Git query failures and
bare/non-repository invocations deny; only interactive hook mode fails open.

## Next action
Execute T-0026: implement D-0015 policy snapshots, meta-rules, and receipts;
then fix cross-layer line/YAML/path/Edit semantics. Keep false pre-receive
claims out of the next release. Promote v0.4 only after the repair gate closes;
its full contract is in
`plans/v0.4-global-coordination.md`. Dogfood against the real home only after
separate explicit approval.

## Gotchas
Homebrew rustc 1.98 is healthy after installing llvm@22; fresh isolated builds
are authoritative again. The old target backup remains at
`/private/tmp/statutor-target-backup.vi3x2C/target`. `assets/` and `notes/` are
pre-existing untracked human work: do not edit/add. DECISIONS keeps writ marker.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/);
crates/statutor remains staged-only under D-0014 until a superseding decision;
plans/archive is frozen; existing global home config is outside this task.
