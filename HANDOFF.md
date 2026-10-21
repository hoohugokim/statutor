<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-21 (UTC) by 15 documentation/package/release checks, independent editorial review, GitHub rendering, and desktop/narrow layout measurements
last_worker: codex
last_machine: unknown
handoff_id: 57e014efb00e443187d60ce57339a5a0
supersedes: f825979d18e44892bc8645f473f1f1da

## Goal
Publish the README redesign approved by the human (T-0055).

## Last verified state
- README is 144 lines, with a compact masthead, badges, navigation, example,
  quickstart, agent chooser, Git setup, and visible coverage limits.
- Four linked guides preserve policy/trust, architecture/API, optional global
  instructions/skills, and worker provenance. Repository links resolve.
- Antigravity setup now names a real checkout location, registers batch edits,
  and describes fail-open behavior and the local Git hook's bypass honestly.
- GitHub Markdown rendering preserves all navigation targets and four images.
  Browser DOM layout has no article overflow at 1200 px and 390 px widths.
- Independent editorial review PASS; 15 focused checks pass, including real
  npm/Cargo payload audits. Runtime code, versions, and policy are unchanged.
- Hardened release remains Python/plugins 0.7.4, npm 0.2.0, and crate 0.1.2.
  PR #2/tag publication and public package verification remain complete.

## Next action
Publish the documentation branch, verify CI, merge, and check remote assets.

## Gotchas
- CLI installation and project initialization do not register agent hooks.
- Hooks fail open; staged checks fail closed. Git hooks allow --no-verify.
- Begin fresh legacy worker sessions after upgrading; restart Claude for its
  already-updated 0.7.4 plugin. Global migration remains a separate opt-in.

## Do not touch
Embedded templates/init profiles; frozen archive; DECISIONS.md header;
root pre-commit metadata. Preserve untracked .agents/, _local/, assets/,
notes/, and plans/v0.4-dogfood.pdf.
