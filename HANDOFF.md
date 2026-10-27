<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-27 by `/opt/homebrew/bin/python3 -m pytest -q` (863 passed, 5 skipped)
last_worker: grok
last_machine: unknown
handoff_id: none
supersedes: adc8ff0ea687dddc32a72682ca45db44

## Goal
Publish GitHub tag v0.7.5 and install that release locally for live dogfood.

## Last verified state
- Python and plugins are 0.7.5. npm stays 0.2.0. The crate stays 0.1.3.
- Cursor is a first-class adapter. Governed MultiEdit and NotebookEdit stay
  denied. Case variants match only the same directory entry. Invalid UTF-8
  is a denial. apply_patch state IDs must advance. Append-only writes use
  the line-subsequence test.
- Pytest on 2026-10-27: 863 passed, 5 skipped. The release gate and the host
  probe still have to pass on this commit before the tag.

## Next action
Run the v0.7.5 release gate and the host probe. Tag and publish only after
both exit 0. Then install the published package with pipx.

## Gotchas
- Hooks fail open on a validate exception. Staged mode fails closed.
- Use Homebrew Python 3.15. The system python3 is 3.9.6.
- Tag v0.7.5 starts publish.yml and uploads to PyPI. Do not move the tag.
- Host pins stay Claude 2.1.296, Codex 0.162.1, and OpenCode 2.1.1.

## Do not touch
Embedded templates and init profiles; plans/archive/; the DECISIONS.md
header; root pre-commit metadata; ROADMAP.md. npm and crates.io stay pending.
Keep untracked .agents/, _local/, assets/, notes/, and plans/v0.4-dogfood.pdf.
