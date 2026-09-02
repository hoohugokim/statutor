<!-- statutor: plane=plan | writer=human | agents read ONLY the section below the marker -->
# ROADMAP

## Current milestone <!-- agent-visible -->
v0.4.0 dogfood: exercise the published portable global instruction and Agent
Skill layer in fresh Claude Code and Codex sessions before adopting OpenCode.
Capture only real findings in `notes/dogfooding.md`; corrective patches must
preserve D-0018's explicit adoption, CAS, backup, and no-clobber guarantees.
Runbook: `plans/v0.4-dogfood.md`.

## Next milestone (human context, agents ignore)
v0.5 "worker provenance" (T-0038..T-0041): answer which harness and machine
most recently worked in a governed project without conflating activity,
attempted work, confirmed mutation, and completed handoff. Combine a private
machine-local activity/lease registry with portable, executor-written HANDOFF
attribution and offline collision lineage; expose stable scoped queries,
Git-ref merge guidance, and host capability gaps without network coordination.
Execution spec: `plans/v0.5-worker-provenance.md`.

## Later (human context, agents ignore)
- A real server-side pre-receive/ref-range validator; `staged` mode cannot inspect a bare repo or pushed refs, and D-0014's staged-only scope must be superseded first
- Additional adapters as hook surfaces stabilize (Codex file-tool events)
- statutor doctor as a GitHub status check; D-record index tooling
