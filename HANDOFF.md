<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-24 by `registry.npmjs.org/statutor → latest 0.1.0; crates.io/api statutor → 0.1.0 bin statutor-staged; pytest 267 passed/10 skipped`

## Goal
Ship statutor v0.3: real registry artifacts (D-0014), repo public, tagged
and published — four enforced surfaces.

## Last verified state
ALL registry artifacts LIVE 2026-08-24, all real per D-0014:
PyPI statutor 0.2.0 · npm statutor@0.1.0 (OpenCode adapter) ·
crates.io statutor 0.1.0 (static statutor-staged floor). Phase 2 done:
kernel color fix, Rust twin byte-identical on 30 conformance scenarios,
CI `rust-conformance` gate active. Only T-0018 remains open.

## Next action
Human: T-0018 — flip the repo public (`gh repo edit hoohugokim/statutor
--visibility public`); optionally claim GitHub org `statutor` + domains.
Then archive plans/registry-claims.md into plans/archive/, bump pyproject
to 0.3.0 (with readme/license metadata already in place), commit, tag
v0.3.0, push — publish.yml verifies tag≡version and publishes tokenless.

## Gotchas
One doctor WARN stands until registry-claims.md archives. Conformance
scenarios needing python-side yaml skip locally (NEEDS_PYAML) but run in
CI's pyyaml leg; rust-conformance job must stay green — it is the Rust
duplicate's license to exist (D-0014). Tests via /opt/homebrew/bin/pytest.
DECISIONS.md keeps its writ header marker. Child harnesses get explicit
cwd always.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/);
crates/statutor scope must stay staged-only (D-0014) — no interactive modes.
