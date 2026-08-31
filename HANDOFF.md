<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-31 by `full pytest 326/5; fresh cargo 6; conformance 54; package audit 3; fmt/diff/compile clean`

## Goal
Repair v0.3's trust/release gaps, then build the specified v0.4 portable user
layer for global instructions and skills across Claude, Codex, and OpenCode.

## Last verified state
v0.3 shipped; the 2026-08-31 audit found lifecycle, trust, and claim blockers.
T-0026 implements D-0015: strict dependency-free policy parsing, committed
HEAD baseline plus index candidate judgment, non-configurable trust roots,
and mode-0600 exact-tree receipts. Physical lines, quoted caps, explicit-CWD
paths, and sized Edit checks now agree across Python/Rust. The floor carries
52 semantic scenarios; malformed policy and Git failures deny. Hooks retain
their outer fail-open boundary. Package cleanup and exact 0.1.1 audits remain.

## Next action
Execute T-0027: define conservative TASKS state semantics, append the decision,
then enforce stable unique IDs and permitted checkbox/detail transitions in
shell, editor, apply_patch, staged Python, and Rust. Keep false pre-receive
claims out of v0.3.1. Promote v0.4 only after the repair gate closes; real-home
dogfood still requires separate explicit approval.

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
