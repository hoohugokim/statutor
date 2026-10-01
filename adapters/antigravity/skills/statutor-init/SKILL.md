---
name: statutor-init
description: Scaffold the statutor ledger (AGENTS/HANDOFF/DECISIONS/TASKS/ROADMAP + .statutor.yaml) in this repo. Use when the user asks to initialize, scaffold, or bootstrap a Statutor ledger.
---

# statutor-init

Initialize this repository as a statutor ledgered repo.

## Procedure

1. Run `statutor init .` (or `python3 -m statutor_core init .`) — it creates the governed
   files, `.statutor.yaml`, `plans/archive/`, `notes/`, and a `CLAUDE.md` compatibility bridge
   importing `@AGENTS.md`, skipping anything that already exists.
   It detects conventional directories from project markers (python/rust/node/docs);
   `--type none` (or `min`) opts out per run and `STATUTOR_INIT_TYPE` per user (D-0024).
2. Interview the user briefly to fill `AGENTS.md` (build/test/lint commands, non-default
   conventions, boundaries). Keep it under 120 lines; refuse derivable content.
3. Seed `TASKS.md` from the user's stated goals with sequential `T-NNNN` ids (starting at `T-0001`).
4. Run `statutor-doctor .` and show the report.
