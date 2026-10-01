---
name: handoff
description: Rewrite HANDOFF.md fresh (overwrite-bounded shift-change note) before ending or compacting a session or delegating tasks to subagents.
---

# handoff

Rewrite `HANDOFF.md` now, following the policy exactly:

## Rules

- OVERWRITE the whole file; never append to prior content. Use `write_to_file` with `Overwrite=True`.
- Max 40 lines. Mandatory sections:
  - `## Goal`
  - `## Last verified state`
  - `## Next action`
  - `## Gotchas`
  - `## Do not touch`
- Actually run the verification command first, then stamp `last_verified: <today> by <that command>`.
- "Next action" must be specific enough for a cold-started session: file paths, commands, expected outcome.
- If anything settled this session belongs in `DECISIONS.md`, append the D-record first, then reference its id here.
- If worker tracking is active:
  - Set `last_worker: antigravity`
  - Mint fresh `handoff_id` via `statutor worker new-id`
  - Set `supersedes` to the prior `handoff_id`
  - Record completion via `statutor worker complete --session <id>`
- Name subagent run IDs or conversation IDs in the body as provenance pointers.
