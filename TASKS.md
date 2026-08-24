<!-- statutor: plane=state | policy=state (doctor-checked) | writer=orchestrator | stable IDs, one line per task -->
# TASKS

- [x] T-0001 Port manual test battery to pytest (`tests/test_kernel.py`: hook, check, bash guard, init idempotence, staged a–e via tmp git repos)
- [x] T-0002 Name-collision sweep for `writ` (PyPI, npm, GitHub, crates); decide final CLI name; record as D-0009
- [x] T-0003 Verify Codex hook registration format on current release (hooks.json vs `[hooks]` table); pin exact snippet in adapters/codex/README.md
- [x] T-0004 Verify OpenCode subagent hook coverage (sst/opencode#5894) on current release; note result in adapters/opencode/README.md
- [x] T-0005 Add SessionEnd/Stop hook to the Claude adapter running `writ-doctor` and surfacing WARNs
- [x] T-0006 Integrate the existing Clawd 5-hour PreToolUse HANDOFF checkpoint hook so its output passes statutor validation (sections + stamp) — CLOSED AS OBSOLETE 2026-08-24 (D-0013): the hook never existed on disk (full sweep: settings, backups, app hooks, history); staleness is already stop_doctor's job and every HANDOFF write is validated; build nothing without a real failure
- [x] T-0007 Tag v0.2.0, push repo, test `/plugin marketplace add` + install flow end-to-end — DONE 2026-08-24: tag pushed & CI verified; plugin swap (marketplace re-point + statutor@hoo-plugins install) completed by human same day
- [x] T-0008 CI (GitHub Actions): pytest + self-dogfood `statutor staged` on this repo per PR
- [x] T-0009 writ_doctor: read budgets/sections from `.writ.yaml` instead of module constants
- [x] T-0010 Investigate loading statutor doctrine into Hermes Agent via its skills (agentskills.io format); enforcement there stays git-floor-only until a hook surface is confirmed — DONE 2026-08-24: pre_tool_call block surface confirmed, plugin adapter shipped; adapter then DROPPED same-day by the D-0012 scope cut (stays closed as history)
- [x] T-0011 Close the apply_patch gap: extend adapters/opencode/statutor.ts allowlist and decide kernel handling of Codex apply_patch `{command: <patch>}` payloads — DONE 2026-08-24: kernel guard_apply_patch parses envelopes (semantics in D-0011); allowlist/matcher widened; residual MCP + Update-section checks stay with the floor
- [x] T-0012 adapters/git/pre-commit vendored fallback points at `.statutor/statutor_core.py` which `statutor init` never creates — vendor it or drop the branch — DROPPED 2026-08-24 (vendoring forks the single kernel, D-0003): hook fails closed with install guidance; hermetic shim tests cover both branches
- [x] T-0013 Generalize statutor_doctor's remaining hardcoded names (DECISIONS.md status check, TASKS.md/plans consumed-plan heuristic) to policy-derived filenames — DONE 2026-08-24: state + append_only rules drive the two filenames (basename-only rule); plans/ stays conventional (init scaffolds it)
- [x] T-0014 Execute the rename once D-0010 records the new name: pyproject, plugin.json, `.writ.yaml` policy filename, hooks/commands/skills, READMEs, repo dir
- [x] T-0015 Claim PyPI `statutor`: build + twine-upload v0.2.0 (runbook plans/registry-claims.md); re-scope the API token to the project afterward
- [ ] T-0016 Publish honest npm placeholder `statutor` 0.0.1 pointing at PyPI + this repo
- [ ] T-0017 Publish honest crates.io placeholder `statutor` 0.0.1 (lib crate, doc-comment reservation)
- [ ] T-0018 After T-0015: flip repo public (`gh repo edit hoohugokim/statutor --visibility public`); optionally claim GitHub org + statutor.dev
- [x] T-0019 Publish real npm package `statutor` 0.1.0 (D-0014): adapters/opencode packaging, README install story (`"plugin": ["statutor"]`), pack + scratch-load verification; human runs publish — AGENT SIDE DONE 2026-08-24: tarball audited; E2E proven in scratch project (config-referenced node_modules load → bash-guard denial reaches the model as tool result); publish = T-0022
- [ ] T-0020 Rust staged-mode floor crate `statutor` (bin `statutor-staged`, yaml-rust2): parity with post-fix run_staged semantics — incl. kernel `_git()` gaining `-c color.ui=false` and un-pinning the quirk test
- [ ] T-0021 Conformance harness (D-0014 license): scripts/gen_staged_fixtures.py (~30 fixtures from K-95..K-118 families), tests/test_conformance_rust.py differential runner, CI rust leg
- [ ] T-0022 Human publish flows: npm publish after T-0019 green; cargo publish only after the CI rust conformance leg is green
