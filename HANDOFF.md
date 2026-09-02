<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-09-02 by `git diff --check && statutor-doctor .`

## Goal
Dogfood published v0.4.0 global instructions and skills across Claude Code,
Codex, and later OpenCode; preserve real findings for corrective patches.

## Last verified state
v0.4.0 is published and installed for real-home dogfood. Claude and Codex
global instruction targets were safely adopted: both are Statutor-owned,
mode 0600, installed, and preserve their original overlays byte-for-byte.
OpenCode remains deliberately unmanaged because its empty overlay would
suppress Claude fallback. D-0020..D-0022 accept v0.5 hybrid provenance: random
machine IDs, local activity/mutation/leases, portable worker+machine HANDOFF
attribution, and unique HANDOFF revision lineage. Sibling revisions from one
base provide offline collision detection and Git-ref merge guidance without a
coordinator. T-0038..T-0041 and the v0.5 plan specify the work. Ledger checks
pass.

## Next action
Test v0.4.0 in fresh Claude and Codex sessions and append only observed issues
to `notes/dogfooding.md`. Curate the OpenCode overlay before adopting it.

## Gotchas
Skill baseline remains 98 occurrences, 14 duplicate groups, three foreign
owners, four known errors, and six warnings; do not fix them incidentally.
`_local/`, `assets/`, `notes/`, and the dogfood PDF are untracked human work.
Active leases will be machine-local; v0.5 will not claim fleet-wide presence.

## Do not touch
Embedded TEMPLATES dict; root `.pre-commit-hooks.yaml`; top-level plugin layout;
plans/archive; existing real-home configuration except separately approved
dogfood operations.
