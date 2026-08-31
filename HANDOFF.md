<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-31 by `full pytest 353/5; doctor suite 47; prior fresh cargo 7/conformance 61/package 3; diff clean`

## Goal
Repair v0.3's trust/release gaps, then build the specified v0.4 portable user
layer for global instructions and skills across Claude, Codex, and OpenCode.

## Last verified state
v0.3 shipped; the 2026-08-31 audit found lifecycle, trust, and claim blockers.
T-0026 implements D-0015's dual-snapshot trust floor and exact-tree receipts.
T-0027 implements D-0016 state identity: existing task IDs survive; checkbox,
detail, and order may change; new IDs advance beyond the committed maximum.
T-0028 makes doctor/Stop aggregate invalid dates, resolve nested marked roots,
and ignore generic AGENTS-only repos. Shell/editor/apply_patch, doctor, and both
floors enforce the state contract. The floor carries 59 semantic scenarios;
malformed policy/Git failures deny. Exact 0.1.1 audits remain green.

## Next action
Execute T-0029's public truth sweep: retract staged-as-pre-receive and static
binary claims, correct matcher/pin/placeholders, and distinguish distribution
channels from enforcement coverage. Then build T-0030's release gate. Real-home
dogfood remains separately gated.

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
