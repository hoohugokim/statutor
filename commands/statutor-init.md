---
description: Scaffold the statutor ledger (AGENTS/HANDOFF/DECISIONS/TASKS/ROADMAP + .statutor.yaml) in this repo
---
Initialize this repository as a statutor ledgered repo.

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/core/statutor_core.py init .` — it creates the governed files, `.statutor.yaml`, `plans/archive/`, `notes/`, and a `CLAUDE.md` importing `@AGENTS.md`, skipping anything that exists.
2. Interview me briefly to fill AGENTS.md (build/test/lint commands, non-default conventions, boundaries). Keep it under 120 lines; refuse derivable content.
3. Seed TASKS.md from my stated goals with `T-NNNN` ids.
4. Run `python3 ${CLAUDE_PLUGIN_ROOT}/core/statutor_doctor.py` and show the report.
