<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-24 by `pytest -q → 238 passed/8 skipped; opencode scratch E2E: bash-guard denial reached model as tool result`

## Goal
Ship statutor v0.3: real registry artifacts (D-0014), repo public, tagged
and published — four enforced surfaces.

## Last verified state
Phase 1 (T-0019) DONE: npm package `statutor` 0.1.0 packaged in
adapters/opencode/ (tarball audited) and E2E-proven in a scratch project —
opencode.json `"plugin": ["./node_modules/statutor/statutor.ts"]` loads,
hook fires, `statutor check` exit 2 surfaces as the model's tool result.
Publish itself is T-0022 (human tokens). Phase 2 next: T-0020 kernel
color fix + Rust floor, T-0021 conformance harness + CI leg.

## Next action
Phase 2 on human go-ahead. Human tails whenever ready: from
adapters/opencode/ run `npm login && npm publish --access public`
(T-0022); registry trio T-0016..T-0018 per plans/registry-claims.md.
Then archive that plan, bump 0.3.0, tag, push (publish.yml publishes).

## Gotchas
Testing a child opencode from inside an opencode session: unset
OPENCODE/OPENCODE_PID or plugins misbehave; give the child an explicit
cwd and its own PATH shim for the statutor CLI (no global install here,
PEP 668). One doctor WARN stands until plans/registry-claims.md archives.
Tests via /opt/homebrew/bin/pytest; two doctor tests skip sans PyYAML.
DECISIONS.md keeps its writ header marker.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/).
