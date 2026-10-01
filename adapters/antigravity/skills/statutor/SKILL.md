---
name: statutor
description: Typed project-ledger discipline for agentic repos in Google Antigravity. Use this skill whenever the user initializes an agentic project, asks to set up AGENTS.md / HANDOFF.md / DECISIONS.md / TASKS.md / ROADMAP.md, mentions "statutor", "ledger", "handoff", "decision record", "ADR", "project memory files", or multi-agent/multi-session coordination — and whenever you are about to create or restructure agent instruction files.
---

# statutor — the project ledger framework

Repo instruction files are a state machine of typed registers, each with a
mutation policy and exactly one writer — enforced by hooks, not by prose.
This skill orients and routes: it fires on ledger-related intent so the
session loads the framework. Authoritative procedures live in the specialized
skills (`statutor-init`, `statutor-doctor`, `handoff`, `decide`), enforcement
in the kernel hooks and git floor — where this file and those disagree, those win.

## The four planes

| Plane | Files | Mutation | Writer |
|---|---|---|---|
| Constitution | AGENTS.md | rare, human-reviewed | human |
| State | HANDOFF.md, TASKS.md | overwrite in place | executor / orchestrator |
| Log | DECISIONS.md | append-only, insertions only | orchestrator / human |
| Plan | ROADMAP.md, plans/*.md | human-owned; consumed → plans/archive/ | human / planner |

## Non-negotiable rules

1. **Constitution stays small.** Soft 120 lines, hard 200 lines (hook-enforced).
   Only what the repo cannot say itself. Never LLM-generate it wholesale;
   grow it one hard-won correction at a time.
2. **HANDOFF.md is a shift-change note.** Overwrite, never append. Max 40
   lines, mandatory sections (Goal / Last verified state / Next action /
   Gotchas / Do not touch), `last_verified: YYYY-MM-DD by <command>` stamp.
   Optional worker provenance block beside the stamp:
   `last_worker: antigravity`, `last_machine: <32-hex-id>`, `handoff_id: <id>`,
   `supersedes: <id>`.
3. **DECISIONS.md is append-only.** Micro-ADRs (`## D-NNNN`, Status/Context/
   Decision/Consequences). Supersede by appending — never edit. Read it
   before re-opening any settled question.
4. **No hand-maintained CHANGELOG.md.** git log + conventional commits.
5. **Procedures live in skills**, never in the constitution.
6. **Single writer per file.** When launching subagents via `invoke_subagent`,
   they must write their findings to `notes/<task-id>.md`.
7. **No shell writes to governed files.** `run_command` with redirects or edits
   to governed files is denied by the bash guard; use `write_to_file` or
   `replace_file_content`.
8. **Drift surfaces at Stop.** The Stop hook runs `statutor-doctor` after each turn
   and reports drift without blocking subsequent turns.

## Session discipline

- Start: read HANDOFF.md → TASKS.md → agent-visible ROADMAP section.
  Read DECISIONS.md before proposing any architecture/tooling change.
- Authority is the certified ledger (those four planes). `notes/`, shell
  scrapes, and unvalidated diffs are raw material: read them for evidence,
  never as state, and promote a finding only through a governed write.
- Before ending or compaction: rewrite HANDOFF.md fresh with a verified
  `last_verified` stamp using the `handoff` skill.
- Any settled choice: append a D-record immediately using the `decide` skill.
- If the hook denies a mutation, comply with the stated policy — never
  work around it.
