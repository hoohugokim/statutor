---
name: statutor
description: Typed project-ledger discipline for agentic repos. Use this skill whenever the user initializes an agentic project, asks to set up AGENTS.md / HANDOFF.md / DECISIONS.md / TASKS.md / ROADMAP.md, mentions "statutor", "ledger", "handoff", "decision record", "ADR", "project memory files", or multi-agent/multi-session coordination — and whenever you are about to create or restructure agent instruction files, even if the user does not name the framework.
---

# statutor — the project ledger framework

Repo instruction files are a state machine of typed registers, each with a
mutation policy and exactly one writer — enforced by hooks, not by prose.

## The four planes

| Plane | Files | Mutation | Writer |
|---|---|---|---|
| Constitution | AGENTS.md (CLAUDE.md = `@AGENTS.md`) | rare, human-reviewed | human |
| State | HANDOFF.md, TASKS.md | overwrite in place | executor / orchestrator |
| Log | DECISIONS.md | append-only, insertions only | orchestrator / human |
| Plan | ROADMAP.md, plans/*.md | human-owned; consumed → plans/archive/ | human / planner |

Non-negotiable rules:

1. **Constitution stays small.** Soft 120 lines, hard 200 (hook-enforced).
   Only what the repo cannot say itself. Never LLM-generate it wholesale;
   grow it one hard-won correction at a time.
2. **HANDOFF.md is a shift-change note.** Overwrite, never append. Max 40
   lines, mandatory sections (Goal / Last verified state / Next action /
   Gotchas / Do not touch), `last_verified: YYYY-MM-DD by <command>` stamp.
   Optional v0.5 provenance block beside the stamp (absent = valid old
   ledger): `last_worker` (stable harness id or `unknown`), `last_machine`
   (opaque machine id or `unknown`), `handoff_id` (fresh random id per
   rewrite, `none` when unattributed), `supersedes` (prior id(s), `none`
   when none). Each rewrite mints a fresh `handoff_id` superseding the
   prior; a reconciliation names every sibling id. Record completion with
   `statutor worker complete --session <id>`; compare refs read-only with
   `statutor worker compare <ref>` — Statutor never merges HANDOFF for you.
   The block records authorship: the completing session should be the
   ledger-writing (usually orchestrating) session on the machine that wrote
   the note. Subagent run ids and remote hosts/branches belong as pointers
   in the note body, not in the schema — the schema stays four fields.
3. **DECISIONS.md is append-only.** Micro-ADRs (`## D-NNNN`, Status/Context/
   Decision/Consequences). Supersede by appending — never edit. Read it
   before re-opening any settled question.
4. **No hand-maintained CHANGELOG.md.** git log + conventional commits.
5. **Procedures live in skills/commands**, never in the constitution.
6. **Single writer per file.** Subagents use `notes/<task-id>.md`.
7. **No shell writes to governed files** (`>>`, `sed -i`, ...) — the bash
   guard denies them; use the editor tools.
8. **Drift surfaces at Stop, not just in-loop.** Claude Code's Stop hook
   (`hooks/stop_doctor.py`) runs `statutor-doctor` after each turn and adds its
   WARN/ERROR lines as context — non-blocking, silent on a clean ledger.

## Scaffolding (/statutor-init or on request)

Run `python3 ${CLAUDE_PLUGIN_ROOT}/core/statutor_core.py init .` (templates are
embedded in the kernel — the single source of truth). Then fill AGENTS.md
interactively (commands → conventions → boundaries; refuse derivable
padding), seed TASKS.md with stable T-NNNN ids, and run the doctor.

## Session discipline

- Start: read HANDOFF.md → TASKS.md → agent-visible ROADMAP section.
  Read DECISIONS.md before proposing any architecture/tooling change.
- Before ending or compaction: rewrite HANDOFF.md fresh with a verified
  `last_verified` stamp.
- Any settled choice: append a D-record immediately (~10 lines).
- If the hook denies a mutation, comply with the stated policy — never
  work around it.
