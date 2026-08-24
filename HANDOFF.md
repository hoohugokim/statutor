<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-24 by `pytest -q → 267 passed/10 skipped; cargo test 4/4; conformance 29≡29; npm statutor@0.1.0 LIVE`

## Goal
Ship statutor v0.3: real registry artifacts (D-0014), repo public, tagged
and published — four enforced surfaces.

## Last verified state
Phase 2 DONE 2026-08-24: kernel `_git()` pins color.ui=false (quirk test
un-pinned); crates/statutor ships `statutor-staged` byte-compatible with
the Python floor; tests/conformance_scenarios.py + test_conformance_rust.py
prove Python ≡ Rust on 30 scenarios (+hostile-gitconfig), CI job
`rust-conformance` enforces it with --locked builds; 4 rust unit tests.
npm statutor@0.1.0 published by human. Suite 267 passed/10 skipped.

## Next action
Human tails: T-0022 cargo publish AFTER the new rust-conformance CI leg is
green on main (push pending at this writing — verify first!). Registry trio
T-0016..T-0018 per plans/registry-claims.md; then archive that plan, bump
0.3.0, tag, push (publish.yml publishes tokenless).

## Gotchas
Conformance scenarios needing python-side .statutor.yaml parsing skip
without PyYAML locally (NEEDS_PYAML set) — they run in CI's pyyaml leg.
One doctor WARN stands until registry-claims archives (now also names
T-0019). Tests via /opt/homebrew/bin/pytest. DECISIONS.md keeps its writ
header marker. When spawning child opencode/harnesses: explicit cwd always
(see Phase 1 incident).

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/);
crates/statutor scope must stay staged-only (D-0014) — no interactive modes.
