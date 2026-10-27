<!-- statutor: plane=plan | writer=human | agents read ONLY the section below the marker -->
# ROADMAP

## Current milestone <!-- agent-visible -->
v0.7.5 candidate: Cursor adapter plus 0.7.4 audit fixes (D-0030).
Python/plugins 0.7.5, npm still 0.2.0, crate 0.1.3. Publication remains a
human step. Release runbook: `docs/releasing.md`.

## Next milestone (human context, agents ignore)
Undecided. Candidates: live-binary E2E automation, host role-signal watch
(revisit the Q5 guard if a host exposes roles), true concurrent-writer
stress test. D-0023 declines a universal skill library; v0.5 execution
spec stays at `plans/archive/v0.5-worker-provenance.md` for reference.

## Later (human context, agents ignore)
- A real server-side pre-receive/ref-range validator; `staged` mode cannot inspect a bare repo or pushed refs, and D-0014's staged-only scope must be superseded first
- Additional adapters as hook surfaces stabilize (Codex file-tool events)
- statutor doctor as a GitHub status check; D-record index tooling
