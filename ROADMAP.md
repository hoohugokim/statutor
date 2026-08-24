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
- crates: Rust staged-floor binary under D-0014's conformance gate (T-0020/T-0021); needs no new D-record
- Server-side pre-receive recipe around the statutor-staged binary (after T-0022)
- Additional adapters as hook surfaces stabilize (Codex file-tool events)
- statutor doctor as a GitHub status check; D-record index tooling
