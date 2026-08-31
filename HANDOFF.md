<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-31 by `v0.4 exact-index gate: pytest 434/3; Rust 7/0; four payload audits; installed-wheel global smoke`

## Goal
Repair v0.3's trust/release gaps, then build the specified v0.4 portable user
layer for global instructions and skills across Claude, Codex, and OpenCode.

## Last verified state
v0.3.1 remains an unpublished candidate at main 9a4aa23. The v0.4 feature
branch completes D-0018/T-0031..36: strict explicit roots and schemas; safe
hash/CAS/backup/restore primitives; reversible instruction and Agent Skill
projection lifecycles; foreign-lock coexistence; stable status/doctor for
precedence, ownership, drift, unsafe links, duplicates, and explicit budgets.
The opt-in fake-profile E2E pins Claude 2.1.251, Codex 0.151.0, and OpenCode
1.18.20. Exact projections, Codex prompt discovery, OpenCode duplicate
collapse, modified-target refusal, and uninstall recovery pass. Claude has no
equivalent offline personal-skill inventory; this limitation is explicit.
Python/plugin 0.4.0 and npm/crate 0.1.1 pass the exact-index release gate:
434/3 Python, Rust 7/0, four package audits, and installed-wheel CLI smoke.

## Next action
Review the v0.4.0 candidate commit. Real-home dogfood is optional and requires
a separate approved plan; tag, push, and publish remain human actions.

## Gotchas
The E2E rehomes every host under a temporary profile and performs no model or
network call; it did not mutate the real home. Homebrew rustc 1.98 is healthy
with llvm@22. `assets/` and `notes/` are untracked human work: do not edit/add.
DECISIONS keeps its historical writ marker.

## Do not touch
Embedded TEMPLATES dict; root `.pre-commit-hooks.yaml`; top-level plugin layout;
crates/statutor remains staged-only under D-0014; plans/archive is frozen;
existing global home config is outside this task.
