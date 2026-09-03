---
description: Rewrite HANDOFF.md fresh (overwrite-bounded shift-change note) before ending or compacting a session
---
Rewrite HANDOFF.md now, following the policy exactly:

- OVERWRITE the whole file; never append to prior content.
- Max 40 lines. Sections: ## Goal, ## Last verified state, ## Next action, ## Gotchas, ## Do not touch.
- Actually run the verification command first, then stamp `last_verified: <today> by <that command>`.
- "Next action" must be specific enough for a cold-started session: file paths, commands, expected outcome.
- If anything settled this session belongs in DECISIONS.md, append the D-record first, then reference its id here.
- If this session is tracked (`statutor worker begin` ran at session start):
  set `last_worker`/`last_machine` to the session values, mint a fresh
  `handoff_id`, set `supersedes` to the baseline id, then run
  `statutor worker complete --session <id>`. Hooks never rewrite this file.
- If reconciling divergent handoffs: run `statutor worker compare <ref>`
  first and name every required id in `supersedes`.
- Ledgers without the v0.5 block remain valid — add it opportunistically,
  never as a drive-by rewrite.

$ARGUMENTS
