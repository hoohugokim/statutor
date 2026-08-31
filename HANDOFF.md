<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-09-01 by `corrected v0.4 exact-index gate: pytest 448/3; Rust 7/0; four payload audits; installed-wheel opt-in/global smoke`

## Goal
Repair v0.3's trust/release gaps, then build the specified v0.4 portable user
layer for global instructions and skills across Claude, Codex, and OpenCode.

## Last verified state
v0.3.1 remains an unpublished candidate at main 9a4aa23. The v0.4 feature
branch completes D-0018/D-0019 and T-0031..37: explicit roots and schemas; safe
hash/CAS/backup/restore primitives; reversible instruction and Agent Skill
projection lifecycles; foreign-lock coexistence; stable status/doctor for
precedence, ownership, drift, unsafe links, duplicates, and explicit budgets.
Automatic adapters now stay silent outside the nearest `.statutor.yaml`; nested
paths, HEAD-policy guidance, and quoted commit-message heredocs are regression
covered. Fake-profile E2E pins Claude 2.1.252, Codex 0.151.0, and OpenCode
1.18.20. Exact projections, Codex prompt discovery, OpenCode duplicate
collapse, modified-target refusal, and uninstall recovery pass. Claude has no
equivalent offline personal-skill inventory; this limitation is explicit.
Python/plugin 0.4.0 and npm/crate 0.1.1 pass the exact-index release gate:
448/3 Python, Rust 7/0, four package audits, and installed-wheel CLI smoke.

## Next action
Review the corrected v0.4.0 candidate, then execute `plans/v0.4-dogfood.md`
phase by phase with separate approval. Tag, push, and publish remain human.

## Gotchas
Real-home read-only baseline has 98 skill occurrences, 14 duplicate groups,
three foreign-owned names, four existing skill errors, and six warnings; do not
"fix" them during dogfood. `_local/`, `assets/`, and `notes/` are untracked
human work. Homebrew rustc 1.98 + llvm@22 is healthy. Keep DECISIONS writ marker.

## Do not touch
Embedded TEMPLATES dict; root `.pre-commit-hooks.yaml`; top-level plugin layout;
crates/statutor remains staged-only under D-0014; plans/archive is frozen;
existing global home config is outside this task.
