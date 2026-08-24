<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-23 by `CI green all 4 legs + PR #1 self-dogfood proven; local 204p/6s, 210p/0s w/ PyYAML`

## Goal
Ship statutor v0.3: CI-verified, published, plugin-installable on all five adapters.

## Last verified state
Rename writ→statutor complete (D-0009/D-0010); repo ~/workbench/statutor,
remote github.com/hoohugokim/statutor (PRIVATE), main @ 6e192d7 (PR #1 merged).
CI proven: first run caught the pristine-scaffold WARN bug (fixed, 3f491db);
all four matrix legs green; PR self-dogfood (`statutor staged` over PR delta)
executed and passed on every leg. Git floor live locally (.git/hooks shim) —
rejected a staged DECISIONS.md deletion in anger. Old writ tree retired
UNMODIFIED at ~/workbench/Writ/writ.

## Next action
Human executes plans/registry-claims.md: T-0015 claim PyPI `statutor` (build +
twine upload), T-0016 npm placeholder, T-0017 crates placeholder, T-0018 flip
repo public — SAME DAY, before announcing the name anywhere. In parallel or
after: reinstall the Claude plugin from ~/workbench/statutor (part of T-0007
rehearsal: /plugin marketplace add ~/workbench/statutor, install
statutor@hoo-plugins). New agent sessions start cold from this file + AGENTS.md.

## Gotchas
PyPI versions are immutable — 0.2.0 is burned once uploaded; polish metadata at
v0.3, not by re-upload. Session hooks may still point at the OLD Writ plugin
until reinstall. DECISIONS.md keeps its `<!-- writ: -->` header marker
(append-only; by design). python3 here is 3.9.6 — test via /opt/homebrew/bin/pytest.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/);
~/workbench/Writ/writ (frozen pre-rename snapshot until the human deletes it).
