<!-- statutor: plane=plan | writer=human | agents read ONLY the section below the marker -->
# ROADMAP

## Current milestone <!-- agent-visible -->
v0.5.0 live on PyPI: exercise worker provenance in real sessions — begin,
attributed rewrite, complete — refresh host pins (Claude 2.1.261 and Codex
0.153.4 observed against 2.1.258 / 0.152.1 pins), and file only real
findings as TASKS. Runbook: `notes/v0.5-release-guide.md`.

## Next milestone (human context, agents ignore)
Undecided. Candidates: live-binary E2E automation, host role-signal watch
(revisit the Q5 guard if a host exposes roles), true concurrent-writer
stress test. D-0023 declines a universal skill library; v0.5 execution
spec stays at `plans/v0.5-worker-provenance.md` for reference.

## Later (human context, agents ignore)
- A real server-side pre-receive/ref-range validator; `staged` mode cannot inspect a bare repo or pushed refs, and D-0014's staged-only scope must be superseded first
- Additional adapters as hook surfaces stabilize (Codex file-tool events)
- statutor doctor as a GitHub status check; D-record index tooling
