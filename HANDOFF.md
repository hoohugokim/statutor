<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-20 by `statutor version` (statutor 0.7.2) + `pytest -q` (594 passed, 2 skipped) + `statutor-doctor .` (clean) + a live OpenCode 2.0.32 session (frozen write and shell redirect denied, plain write allowed)
last_worker: opencode
last_machine: 1befd044f2ccc95033f353b2b7468adc
handoff_id: 4d59cf6d40ca8ed459ba311cc5199795
supersedes: 6a31c5040e947dbe6373b9e59d99723c

## Goal
Ship the OpenCode 2.x adapter (D-0027, T-0047) on top of the pending v0.7.2
Antigravity scoping work (T-0046), then commit and release.

## Last verified state
- `adapters/opencode/statutor.ts` default-exports `{ id, setup, server }`:
  `ctx.tool.hook("execute.before")` (2.x) and `"tool.execute.before"` (1.x);
  maps `shell`/`path`/`patchText` to the kernel's names; argv spawn, deny
  only on exit code 2, fail open otherwise.
- Live 2.0.32 session: a frozen `write` and a `shell` redirect were denied,
  an ordinary write passed, and a directory without `.statutor.yaml` stayed
  silent. The `server()` path behaves identically in the test harness.
- `tests/test_adapter_opencode.py` adds 7 checks; npm adapter bumped to 0.2.0;
  release-gate and payload tests aligned. Full suite 594 passed/2 skipped.
- The v0.7.2 Antigravity work (T-0046) is still uncommitted.

## Next action
1. Commit v0.7.2 plus T-0047/D-0027; publish `statutor@0.2.0` (human), then
   repoint the global config to `"plugins": ["statutor@0.2.0"]`.

## Gotchas
- 2.x config entries need a package name or a directory; a bare `.ts` path
  logs `configured plugin path must be a directory`.
- 2.x validates the default export; a function default or named-only export
  fails at load, not at import.

## Do not touch
Embedded TEMPLATES/INIT_PROFILES; root `.pre-commit-hooks.yaml`; plugin
layout; plans/archive.
