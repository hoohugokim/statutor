<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-31 by `full pytest 347/5; fresh cargo 7; conformance 61; package audit 3; doctor/fmt/diff clean`

## Goal
Repair v0.3's trust/release gaps, then build the specified v0.4 portable user
layer for global instructions and skills across Claude, Codex, and OpenCode.

## Last verified state
v0.3 shipped; the 2026-08-31 audit found lifecycle, trust, and claim blockers.
T-0026 implements D-0015's dual-snapshot trust floor and exact-tree receipts.
T-0027 implements D-0016 state identity: existing task IDs survive; checkbox,
detail, and order may change; new IDs advance beyond the committed maximum.
Shell/editor/apply_patch, doctor, and both floors enforce the contract. The
floor carries 59 semantic scenarios; malformed policy/Git failures deny and
hooks retain their outer fail-open boundary. Exact 0.1.1 audits remain green.

## Next action
Execute T-0028: make doctor/Stop aggregate safely across invalid dates and
policy drift, resolve nested roots, ignore generic AGENTS-only repos, and remove
stale command text. Then perform T-0029's public truth sweep. Keep false
pre-receive claims out of v0.3.1; real-home dogfood remains separately gated.

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
