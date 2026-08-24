<!-- statutor: plane=state | policy=state (doctor-checked) | writer=orchestrator | stable IDs, one line per task -->
# TASKS

- [x] T-0001 Port manual test battery to pytest (`tests/test_kernel.py`: hook, check, bash guard, init idempotence, staged a–e via tmp git repos)
- [x] T-0002 Name-collision sweep for `writ` (PyPI, npm, GitHub, crates); decide final CLI name; record as D-0009
- [x] T-0003 Verify Codex hook registration format on current release (hooks.json vs `[hooks]` table); pin exact snippet in adapters/codex/README.md
- [x] T-0004 Verify OpenCode subagent hook coverage (sst/opencode#5894) on current release; note result in adapters/opencode/README.md
- [x] T-0005 Add SessionEnd/Stop hook to the Claude adapter running `writ-doctor` and surfacing WARNs
- [ ] T-0006 Integrate the existing Clawd 5-hour PreToolUse HANDOFF checkpoint hook so its output passes statutor validation (sections + stamp)
- [ ] T-0007 Tag v0.2.0, push repo, test `/plugin marketplace add` + install flow end-to-end
- [x] T-0008 CI (GitHub Actions): pytest + self-dogfood `statutor staged` on this repo per PR
- [x] T-0009 writ_doctor: read budgets/sections from `.writ.yaml` instead of module constants
- [ ] T-0010 Investigate loading statutor doctrine into Hermes Agent via its skills (agentskills.io format); enforcement there stays git-floor-only until a hook surface is confirmed
- [ ] T-0011 Close the apply_patch gap: extend adapters/opencode/statutor.ts allowlist and decide kernel handling of Codex apply_patch `{command: <patch>}` payloads (git floor covers meanwhile)
- [ ] T-0012 adapters/git/pre-commit vendored fallback points at `.statutor/statutor_core.py` which `statutor init` never creates — vendor it or drop the branch (README documents the mismatch)
- [ ] T-0013 Generalize statutor_doctor's remaining hardcoded names (DECISIONS.md status check, TASKS.md/plans consumed-plan heuristic) to policy-derived filenames
- [x] T-0014 Execute the rename once D-0010 records the new name: pyproject, plugin.json, `.writ.yaml` policy filename, hooks/commands/skills, READMEs, repo dir
- [x] T-0015 Claim PyPI `statutor`: build + twine-upload v0.2.0 (runbook plans/registry-claims.md); re-scope the API token to the project afterward
- [ ] T-0016 Publish honest npm placeholder `statutor` 0.0.1 pointing at PyPI + this repo
- [ ] T-0017 Publish honest crates.io placeholder `statutor` 0.0.1 (lib crate, doc-comment reservation)
- [ ] T-0018 After T-0015: flip repo public (`gh repo edit hoohugokim/statutor --visibility public`); optionally claim GitHub org + statutor.dev
