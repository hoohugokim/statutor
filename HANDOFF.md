<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-24 by `pypi.org/pypi/statutor/json → 0.2.0 live (whl + sdist); CI green all four legs`

## Goal
Ship statutor v0.3: CI-verified, published, plugin-installable on all five adapters.

## Last verified state
PyPI `statutor` 0.2.0 is LIVE (T-0015 done). Repo github.com/hoohugokim/statutor,
main pushed, CI green on all four legs incl. the PR self-dogfood (T-0008).
Rename complete (D-0009/D-0010); git floor live locally (.git/hooks shim).
Old writ tree at ~/workbench/Writ is approved for deletion by the human —
nothing in this repo references it; only the stale plugin install points there.

## Next action
Human: T-0016 npm placeholder + T-0017 crates placeholder (runbook
plans/registry-claims.md), T-0018 flip repo public. Then the plugin swap:
/plugin marketplace remove the old writ path, /plugin marketplace add
~/workbench/statutor, install statutor@hoo-plugins (first half of T-0007).
New agent sessions start cold from this file + AGENTS.md and work the open
TASKS.md queue (T-0006, T-0007, T-0010..T-0013, T-0016..T-0018).

## Gotchas
PyPI versions are immutable — 0.2.0 is burned; metadata polish lands as v0.3,
not a re-upload. npm/crates stay HONEST placeholders for now; the promotion
intents live in ROADMAP "Later" (npm → real OpenCode plugin after T-0011;
crates → needs a D-record against D-0003's single-kernel rule). DECISIONS.md
keeps its `<!-- writ: -->` marker (append-only). python3 is 3.9.6 — run tests
via /opt/homebrew/bin/pytest.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/).
