# Statutor Ledger Rules for Antigravity

Statutor is a typed project-ledger framework: repo instruction files are a
state machine of typed registers, each with a mutation policy and exactly one
writer — enforced by lifecycle hooks and the git floor, not by prose.

## The Four Planes

| Plane | Files | Mutation | Writer |
|---|---|---|---|
| Constitution | AGENTS.md (GEMINI.md) | rare, human-reviewed | human |
| State | HANDOFF.md, TASKS.md | overwrite in place | executor / orchestrator |
| Log | DECISIONS.md | append-only, insertions only | orchestrator / human |
| Plan | ROADMAP.md, plans/*.md | human-owned; consumed → plans/archive/ | human / planner |

## Invariants

1. **Constitution stays small.** Soft 120 lines, hard 200 lines (hook-enforced).
   Only what the repository cannot say itself. Refuse derivable padding.
2. **HANDOFF.md is a shift-change note.** Overwrite, never append. Max 40
   lines, mandatory sections (Goal / Last verified state / Next action /
   Gotchas / Do not touch), `last_verified: YYYY-MM-DD by <command>` stamp.
   Optional worker attribution: `last_worker: antigravity`, `last_machine: <id>`.
3. **DECISIONS.md is append-only.** Micro-ADRs (`## D-NNNN`, Status/Context/
   Decision/Consequences). Supersede by appending — never edit. Read it
   before re-opening any settled question.
4. **TASKS.md preserves task identity.** Stable `T-NNNN` IDs; one line per task.
   Never delete or renumber existing tasks. New IDs must advance.
5. **No hand-maintained CHANGELOG.md.** git log + conventional commits.
6. **Single writer per file.** Subagents spawned via `invoke_subagent` must write
   their work and notes to `notes/<task-id>.md`, never directly to governed registers.
7. **No shell writes to governed files.** `run_command` with write-ish patterns
   (`>`, `>>`, `sed -i`, `tee`) touching governed files is denied by the bash guard;
   use `write_to_file` or `replace_file_content`.
8. **Drift surfaces at Stop.** The Stop hook runs `statutor-doctor` and reports drift
   without trapping the agent in infinite loops.
