<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-31 by `pytest 360/5; doctor/diff clean; prior release gate 362/3 + Rust 7 + artifact/CLI smoke`

## Goal
Repair v0.3's trust/release gaps, then build the specified v0.4 portable user
layer for global instructions and skills across Claude, Codex, and OpenCode.

## Last verified state
v0.3.1 is a verified, unpublished release candidate at main 9a4aa23. D-0015
through D-0017 close trust, state-identity, drift, and public-claim gaps. The
exact-index gate prepares Python/plugin 0.3.1, audits four package formats,
installs the wheel, and gates tag parity. D-0018 now accepts the bounded v0.4
portable user layer: human canonical sources, whole-file/tree projections,
CAS receipts/backups, stable diagnostics, and fake-home-only implementation.

## Next action
Implement T-0032's zero-dependency resolver, versioned config/receipt schemas,
deterministic safe-tree hashing, locks/journals, atomic compare-and-swap writes,
backups, and restore primitives under explicit fake roots.

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
