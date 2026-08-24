<!-- statutor: plane=plan | writer=human | agents read ONLY the section below the marker -->
# ROADMAP

## Current milestone <!-- agent-visible -->
v0.3 "hardened + publishable": pytest suite green in CI (T-0001, T-0008),
names verified (T-0002), Codex/OpenCode adapter claims re-verified on real
current releases (T-0003, T-0004), plugin install flow tested end-to-end
(T-0007). Done means: a stranger can `pipx install` + `/plugin install` and
get enforced ledgers on Claude Code, OpenCode, and the git floor without
reading this conversation.

## Later (human context, agents ignore)
- npm: promote the placeholder to a REAL package — ship the OpenCode adapter
  as an installable plugin once T-0011 closes and the adapter surface
  stabilizes; record the promotion as a D-record
- crates: promote the placeholder to a REAL artifact — candidate is a native
  `statutor staged` binary for server-side pre-receive floors; that would
  duplicate validate(), so it requires a D-record resolving the D-0003
  single-kernel tension (e.g., a port gated on the Python kernel's pytest
  battery in CI)
- Server-side pre-receive recipe for the git floor (Python kernel first)
- Additional adapters as hook surfaces stabilize (Codex file-tool events, Hermes Agent)
- statutor doctor as a GitHub status check; D-record index tooling
