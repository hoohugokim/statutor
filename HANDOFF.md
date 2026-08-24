<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-24 by `pytest -q → 238 passed/8 skipped; statutor staged clean; TASKS queue empty except human registry trio`

## Goal
Ship statutor v0.3: registry placeholders claimed, repo public, tagged and
published via trusted publishing — four enforced surfaces (D-0012).

## Last verified state
Agent queue EMPTY 2026-08-24. Everything agent-side is done and pushed:
apply_patch parsed by the kernel (D-0011), pre-commit fails closed, doctor
filenames policy-derived, stop-hook sentinel follows renames, Hermes
dropped (D-0012), T-0006 closed wontfix (D-0013 — no periodic checkpoint
mechanism; staleness is the doctor's job). v0.3 prep landed (metadata,
LICENSE, publish.yml). T-0007 closed incl. human plugin swap.

## Next action
Human only: T-0016 npm + T-0017 crates placeholders and T-0018 repo
public per plans/registry-claims.md; then archive that plan, bump
pyproject to 0.3.0, commit, tag v0.3.0, push — publish.yml verifies
tag≡version and publishes OIDC-tokenless. Human AGENTS.md/ROADMAP.md
edits were still uncommitted at this writing — commit or discard them.

## Gotchas
One doctor WARN stands until plans/registry-claims.md archives (its own
done-condition names all four registry tasks). No global CLI install
locally (PEP 668); local floor is the in-repo shim. Tests via
/opt/homebrew/bin/pytest; two doctor tests skip without PyYAML locally.
DECISIONS.md keeps its writ header marker. ROADMAP promotion intents
(npm plugin, Rust floor) need D-records before any code exists.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/).
