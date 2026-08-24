---
description: Rewrite HANDOFF.md fresh (overwrite-bounded shift-change note) before ending or compacting a session
---
Rewrite HANDOFF.md now, following the policy exactly:

- OVERWRITE the whole file; never append to prior content.
- Max 40 lines. Sections: ## Goal, ## Last verified state, ## Next action, ## Gotchas, ## Do not touch.
- Actually run the verification command first, then stamp `last_verified: <today> by <that command>`.
- "Next action" must be specific enough for a cold-started session: file paths, commands, expected outcome.
- If anything settled this session belongs in DECISIONS.md, append the D-record first, then reference its id here.

$ARGUMENTS
