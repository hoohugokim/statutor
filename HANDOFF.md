<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-23 by `CI green on push run 32682110629's successor + PR #1 checks (all legs)`

## Goal
Ship statutor v0.3: CI-verified, published, plugin-installable on all five adapters.

## Last verified state
Rename writ→statutor executed (D-0009/D-0010, T-0014); repo at
~/workbench/statutor, remote github.com/hoohugokim/statutor (PRIVATE), main
pushed. CI PROVEN: first run caught a real pyyaml=false bug (pristine-scaffold
.statutor.yaml tripping the unapplied-policy WARN → Stop hook spoke); fixed in
3f491db; second run green on all four legs. PR #1 (chore: .gitignore) proved
the pull_request self-dogfood step end-to-end (`statutor staged` over the PR
delta, all legs) — T-0008 closed. Local: 204 passed/6 skipped; 210/0 with
PyYAML. Git floor live on this repo (.git/hooks shim): rejected a staged
DECISIONS.md deletion in anger. Old writ tree retired UNMODIFIED.

## Next action
Human: (1) merge PR #1 (merge was classifier-blocked for the agent);
(2) claim PyPI `statutor` + npm/crates placeholders TODAY, then flip the repo
public (`gh repo edit hoohugokim/statutor --visibility public`);
(3) reinstall the Claude plugin from ~/workbench/statutor. Then T-0007.

## Gotchas
PyPI is first-come; do not announce before claiming. The session's installed
plugin still points at the OLD Writ path — reinstall before trusting in-loop
hooks here. DECISIONS.md keeps its `<!-- writ: -->` header marker (append-only;
by design). python3 here is 3.9.6 — run tests via /opt/homebrew/bin/pytest.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/);
~/workbench/Writ/writ (frozen pre-rename snapshot until the human deletes it).
