<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-21 (UTC) by release/tag CI, exact-index gate (769 passed, zero skips), registry payload comparisons, clean installs, and runtime smoke
last_worker: codex
last_machine: unknown
handoff_id: f825979d18e44892bc8645f473f1f1da
supersedes: b2bb593f0c7b485b814379cf546642cd

## Goal
Completed hardened Python/plugins 0.7.4, npm adapter 0.2.0, and crate 0.1.2
(D-0029, T-0049..T-0054), following the v0.7.3 audit. All channels verified.

## Last verified state
- Floor preserves worktree, Git mode, strict policy, glob, and state identity.
  Independent checks: 109 differential cases, 307 policies, 149,481 globs.
- Global lifecycle binds logical/resolved targets and rolls back safe owned
  replacements. Global tests: 100 passed. Worker family: 90 passed.
- Native batch edits preserve CRLF. Stop fails open on malformed metadata.
  Gate snapshots exact index; original HEAD/tree authorizes trust receipts.
- Runtime review PASS+NOTES and Standards PASS through 7a6f25c; no findings.
  Completed specifications moved unchanged into plans/archive.
- Current fake-profile probes: Claude 2.1.296, Codex 0.162.1, OpenCode 2.1.1.
  Rust 1.75 release build, seven unit tests, and conformance pass.
- PR #2 merged as 0572042; tag v0.7.4 CI and PyPI publisher both passed.
- Public payloads match the tag; registry installs and hook tests pass. GitHub has all four artifacts.

## Next action
No release work remains. Select the next milestone with the human.
Local CLI and Claude plugin are 0.7.4; restart Claude to load the plugin.

## Gotchas
- Legacy worker sessions lack ledger scope: begin a new session to mutate.
- Global probes prove only their reported native surfaces; Claude has no
  offline personal-skill catalog. Real-home global migration is separate.

## Do not touch
Embedded TEMPLATES/INIT_PROFILES; frozen archive; DECISIONS.md header;
root pre-commit metadata. Preserve untracked .agents/, _local/, assets/,
notes/, and plans/v0.4-dogfood.pdf.
