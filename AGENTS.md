<!-- statutor: plane=constitution | policy=constitution | writer=human | budget: soft 120 / hard 200 lines -->
# AGENTS.md — statutor

Statutor (formerly writ; D-0009/D-0010) is a typed project-ledger framework
for agentic repos: four planes (constitution/state/log/plan), one writer per
file, mutation policies enforced by hooks and the git floor, not by prose.
This repo is the kernel plus adapters, and doubles as the Claude Code plugin.
It governs itself with its own ledger (dogfood is mandatory).

## Commands
- Dev install: `pip install -e .` (console scripts `statutor`, `statutor-doctor`)
- Tests: `pytest -q` (baseline 203 passed/6 skipped; PyYAML-absence skips are expected)
- Lint ledger: `statutor-doctor .` ; git floor: `statutor staged .`

## Conventions that differ from defaults
- Kernel (`core/statutor_core.py`) has ZERO third-party deps; PyYAML strictly optional.
- Hook mode must FAIL OPEN — a kernel bug must never break a session.
- Templates live ONLY embedded in the kernel (TEMPLATES dict). Never create
  a templates/ directory; it would fork the source of truth.
- Python for anything reading JSON on stdin; fish only for interactive
  wrappers (user runs fish on Pop!_OS).
- American English; SI units; doc claims carry inline links that survive
  export to PDF/MD/DOCX.

## Pitfalls (hard-won, one line each)
- `/bin/sh` heredoc scripts: no brace expansion — `mkdir -p a/{b,c}` makes a literal `{b,c}` dir.
- apply_patch is kernel-parsed since D-0011; the real remaining hole is MCP tool names – the floor covers them.
- `.pre-commit-hooks.yaml` must stay at the REPO ROOT or `repo:` consumers break.
- Repo root IS the Claude plugin root: hooks/, commands/, skills/ stay top-level.
- In git-floor tests, restore worktree with `git reset -q --hard`, not checkout-then-reset ordering.
- DECISIONS.md keeps its original `<!-- writ: -->` header marker: append-only forbids editing it (history is history).

## Boundaries
- `plans/archive/` is frozen (hook + floor enforce; `git mv` INTO it is allowed).
- No hand-maintained CHANGELOG.md — conventional commits + git log.
- DECISIONS.md is append-only: read it before re-opening any settled question.
