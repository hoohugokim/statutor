---
description: Append a micro-ADR (D-record) to DECISIONS.md — append-only, supersede-never-edit
---
Record a decision in DECISIONS.md.

1. Read DECISIONS.md; determine the next `D-NNNN` id.
2. Append (never modify existing records), ~10 lines max:

## D-NNNN — <title>
**Status:** accepted
**Context:** <the forces, one or two lines>
**Decision:** <what was chosen, one line>
**Consequences:** <what this constrains or unlocks>

3. If this supersedes an earlier record, add `**Supersedes:** D-MMMM` to the NEW record — do not edit the old one; the hook denies it anyway.

Decision to record: $ARGUMENTS
