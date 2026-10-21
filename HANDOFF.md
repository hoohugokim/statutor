<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-21 by `pytest -q` (610 passed, 2 skipped) + `statutor-doctor .` + live `grok 1.0.62 (1474f9cbdd91)`
last_worker: grok
last_machine: 1befd044f2ccc95033f353b2b7468adc
handoff_id: 9785fb98991890e23190f9fc76744a28
supersedes: 220024407db275c3db219f4a4da832eb

## Goal
Publish patch 0.7.3 (D-0028, T-0048): Grok vocabulary map, README lead,
and GitHub Releases from the existing tags through v0.7.3.

## Last verified state
- Kernel maps `write`, `search_replace`, `run_terminal_command`, `StrReplace`,
  and `Shell`. One Stop continues on `end_turn`; the next Stop and `shutdown`
  stay silent. Live 1.0.62 probe: append-only write denied, HANDOFF shell
  redirect denied, ordinary write allowed, unmarked repo silent.
- README lead names the four planes and the harnesses. Pre-commit pin is
  v0.7.3. No v0.7.0 tag: that number lived on two docs commits. v0.7.1 is
  the first tagged 0.7 release and carries the Antigravity adapter.
- Suite 610 passed / 2 skipped. npm stays 0.2.0; cargo stays 0.1.1.

## Next action
PyPI publish of 0.7.3 and npm publish of `statutor@0.2.0` remain human steps.
Reinstall `statutor@hoo-plugins` so sessions stop loading the 0.6.0 cache.

## Gotchas
- Enabled plugin cache is `~/.claude/plugins/cache/hoo-plugins/statutor/0.6.0`.
  Its doctor rejects `last_worker: grok`. A project `.grok/hooks` snippet and
  that plugin both fire.
- The probe saw no subagent PreToolUse. MCP `use_tool` and bash-mode `!`
  stay on the git floor.

## Do not touch
Embedded TEMPLATES/INIT_PROFILES; plans/archive; the DECISIONS.md header;
root `.pre-commit-hooks.yaml`. Untracked `_local/`, `assets/`, loose
`notes/`, `.agents/`, `plans/v0.4-dogfood.pdf`.
