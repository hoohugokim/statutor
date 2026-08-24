<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-23 by `/opt/homebrew/bin/pytest -q in ~/workbench/statutor (203p/6s)`

## Goal
Ship statutor v0.3: CI-verified, published, plugin-installable on all five adapters.

## Last verified state
Rename writ→statutor executed (D-0009/D-0010, T-0014): repo lives at
~/workbench/statutor; dist/CLI `statutor`, doctor `statutor-doctor`, policy file
`.statutor.yaml`, prefixes `[statutor]`/`STATUTOR`, plugin statutor@hoo-plugins.
Suite green post-rename: 203 passed/6 skipped (PyYAML-absence skips; the pixi
py3.12+pyyaml leg runs all 209). Old tree at ~/workbench/Writ/writ retired
UNMODIFIED as the pre-rename snapshot. git initialized with a local pre-commit
floor shim; remote: github.com/hoohugokim/statutor (private).

## Next action
Human claims PyPI `statutor` (+ npm/crates placeholders) TODAY — repo stays
private until claimed, then flip public (`gh repo edit --visibility public`).
Reinstall the Claude plugin from the new path. Then T-0007 rehearsal.

## Gotchas
PyPI is first-come; do not announce before claiming. The session's installed
plugin still points at the OLD Writ path — reinstall before trusting in-loop
hooks here. DECISIONS.md keeps its `<!-- writ: -->` header marker (append-only;
by design). python3 here is 3.9.6 — run tests via /opt/homebrew/bin/pytest.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/);
~/workbench/Writ/writ (frozen pre-rename snapshot until the human deletes it).
