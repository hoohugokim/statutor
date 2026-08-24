<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-24 by `pytest -q → 238 passed/8 skipped; statutor staged clean; v0.2.0 live on PyPI; plugin re-installed from this tree`

## Goal
Ship statutor v0.3: published, registry placeholders in place, repo public —
enforced ledgers on Claude Code, OpenCode, Codex, and the git floor (D-0012).

## Last verified state
Agent queue fully drained + scope cut executed 2026-08-24: apply_patch is
kernel-parsed (D-0011), pre-commit hook fails closed without the CLI,
doctor filenames policy-derived, stop-hook sentinel follows renames.
Hermes adapter DROPPED (D-0012) — four supported surfaces remain.
T-0007 closed: v0.2.0 tagged/pushed AND plugin flow verified by human.
v0.3 prep landed: pyproject metadata (PEP 639 MIT), LICENSE, publish.yml
(OIDC trusted publishing, tag/version guard). Suite green; floor clean.

## Next action
Human-only tail, per plans/registry-claims.md: T-0016 npm placeholder,
T-0017 crates placeholder, T-0018 flip repo public (+optional org/domains).
One-time PyPI UI step already done? If not: register pending trusted
publisher (hoohugokim/statutor, workflow publish.yml). Then archive that
plan and cut v0.3: bump version → tag v0.3.0 → push (publish.yml does the
rest; 0.2.0 is burned).

## Gotchas
One doctor WARN expected until plans/registry-claims.md archives (its own
done-condition names all four registry tasks). ROADMAP/AGENTS.md edits are
the human's in-flight changes — never stage them blindly. No global CLI
install locally (PEP 668); local floor is the in-repo shim. Tests via
/opt/homebrew/bin/pytest; two doctor tests skip without PyYAML locally.
DECISIONS.md keeps its writ header marker.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/).
