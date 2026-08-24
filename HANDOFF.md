<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-24 by `pypi.org/pypi/statutor/json → 0.3.0 live (whl+sdist, trusted-published); pytest 267 passed/10 skipped; doctor clean`

## Goal
statutor v0.3 SHIPPED AND VERIFIED: public repo, three registries carrying
real artifacts, four enforced surfaces, queue empty.

## Last verified state
EVERYTHING DONE 2026-08-24. PyPI serves statutor 0.3.0 (published
tokenless by publish.yml on the v0.3.0 tag — first run of that pipeline).
npm statutor@0.1.0 (OpenCode adapter); crates.io statutor 0.1.0
(statutor-staged static floor). Repo public. TASKS empty; ledger doctor
clean; plans all archived. Kernel color fix in; Rust twin byte-identical
under the CI conformance gate (D-0014).

## Next action
Nothing owed. Post-release ideas live in ROADMAP "Later" (server-side
pre-receive recipe around statutor-staged, doctor as GitHub status check,
D-record index tooling, Codex file-tool adapter events). Homebrew tap and
APT channels: deliberately deferred — revisit only on real demand; each
channel adds a permanent release-tax workflow.

## Gotchas
PyPI versions immutable (0.2.0/0.3.0 burned). rust-conformance CI green
is the Rust duplicate's license to exist (D-0014) — never skip it.
Conformance yaml scenarios skip locally without PyYAML but run in CI.
Tests via /opt/homebrew/bin/pytest. DECISIONS.md keeps its writ header
marker. Child harnesses get explicit cwd always.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/);
crates/statutor scope must stay staged-only (D-0014) — no interactive modes.
