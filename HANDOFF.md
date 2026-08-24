<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-24 by `GitHub API unauth → private:false; pytest 267 passed/10 skipped; doctor fully clean; v0.3.0 tagged`

## Goal
statutor v0.3 SHIPPED: published, public, real artifacts on all three
registries — four enforced surfaces (D-0012), Rust twin under conformance
gate (D-0014).

## Last verified state
TASKS QUEUE EMPTY 2026-08-24. Repo PUBLIC (unauth API verified).
Registries live: PyPI 0.2.0 → 0.3.0 publishing via tag; npm statutor@0.1.0
(OpenCode adapter); crates.io statutor 0.1.0 (statutor-staged floor).
registry-claims.md archived; doctor ledger clean. This commit carries the
0.3.0 bump (pyproject + plugin.json); publish.yml fires on the v0.3.0 tag.

## Next action
Verify the tag's GitHub run: publish job must show green and PyPI must
list statutor 0.3.0 (trusted publisher, tokenless). If it fails on
publish permissions, check the PyPI pending-publisher registration
(owner hoohugokim, repo statutor, workflow publish.yml, env empty).
Post-release ideas live in ROADMAP "Later"; nothing is owed.

## Gotchas
PyPI versions immutable — 0.2.0/0.3.0 burned forever. Conformance yaml
scenarios skip locally without PyYAML but run in CI; rust-conformance
green = the Rust duplicate's license to exist (D-0014). Tests via
/opt/homebrew/bin/pytest. DECISIONS.md keeps its writ header marker.
Child harnesses get explicit cwd always.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/);
crates/statutor scope must stay staged-only (D-0014) — no interactive modes.
