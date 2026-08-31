<!-- statutor: plane=plan | writer=human | agents read ONLY the section below the marker -->
# ROADMAP

## Current milestone <!-- agent-visible -->
v0.3.1 "truthful trust floor" (T-0023..T-0030): repair the release payload,
make every record lifecycle and policy-source check match the public doctrine,
and retract the nonfunctional pre-receive claim until a real ref-range mode
exists. Done means clean wheel/sdist/npm/crate payloads are tested before
publication; no governed record or policy can disappear, move, or evade the
floor through unstaged config, binary diff behavior, or ignored git failures;
and every install snippet is copy-pasteable and current. Execution spec:
`plans/v0.3.1-truth-floor.md`.

## Next milestone (human context, agents ignore)
v0.4 "portable user layer" (T-0031..T-0036): one human-owned global
instruction source and one managed Agent Skill lifecycle, projected safely to
Claude Code, Codex, and stable OpenCode with receipts, collision/drift
diagnostics, reversible adoption, and no clobbering. Full proposed contract:
`plans/v0.4-global-coordination.md`.

## Later (human context, agents ignore)
- A real server-side pre-receive/ref-range validator; `staged` mode cannot inspect a bare repo or pushed refs, and D-0014's staged-only scope must be superseded first
- Additional adapters as hook surfaces stabilize (Codex file-tool events)
- statutor doctor as a GitHub status check; D-record index tooling
