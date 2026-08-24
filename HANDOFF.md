<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-08-24 by `pytest -q → 245 passed/6 skipped; statutor staged clean; v0.2.0 tag on origin`

## Goal
Ship statutor v0.3: CI-verified, published, plugin-installable on all five adapters.

## Last verified state
Open agent queue drained 2026-08-24: T-0011 kernel parses apply_patch
envelopes (D-0011; opencode allowlist + codex matcher widened), T-0012
pre-commit hook fails closed without the CLI, T-0013 doctor filenames are
policy-derived, T-0010 Hermes gets full in-loop enforcement via the new
plugin adapter (pre_tool_call block directive, verified from hermes-agent
source). T-0007 half-done: v0.2.0 tagged at the published tree + pushed;
interactive /plugin swap remains. Suite 245 passed/6 skipped; floor clean.

## Next action
Human: (1) re-scope or drop T-0006 — the "Clawd 5-hour checkpoint hook"
referenced there does not exist on disk; (2) finish T-0007 in Claude Code:
/plugin marketplace remove the old writ path, add ~/workbench/statutor,
install statutor@hoo-plugins; (3) T-0016/T-0017/T-0018 registry steps per
plans/registry-claims.md. Then archive that plan and cut v0.3 (metadata
polish + trusted-publisher workflow; 0.2.0 is burned).

## Gotchas
Two doctor WARNs are expected until the plans above archive (each names its
own completion condition). AGENTS.md pitfall about apply_patch/MCP allowlist
misses is now stale — writer=human, needs a human edit line. The local git
floor is an in-repo shim (.git/hooks/pre-commit); no global CLI install
(PEP 668 blocks brew pip). python3 is 3.9.6 — run tests via
/opt/homebrew/bin/pytest. DECISIONS.md keeps its writ header marker.

## Do not touch
Embedded TEMPLATES dict (single source — no templates/ dir); root location of
`.pre-commit-hooks.yaml`; top-level plugin layout (hooks/, commands/, skills/).
