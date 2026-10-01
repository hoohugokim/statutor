---
name: decide
description: Append a micro-ADR (D-record) to DECISIONS.md — append-only, supersede-never-edit. Use when any architectural, framework, or tooling decision is settled.
---

# decide

Record an architectural or design decision in `DECISIONS.md`.

## Procedure

1. Read `DECISIONS.md` to determine the next `D-NNNN` id.
2. Append (never modify or delete existing records), ~10 lines max:

```markdown
## D-NNNN — <title>
**Status:** accepted
**Context:** <the forces, one or two lines>
**Decision:** <what was chosen, one line>
**Consequences:** <what this constrains or unlocks>
```

3. If this supersedes an earlier record, add `**Supersedes:** D-MMMM` to the new record — do not edit the old one (the hook and git floor will deny edits).
4. Use `write_to_file` with `Append=True` or `replace_file_content` ensuring all existing content is preserved verbatim.
