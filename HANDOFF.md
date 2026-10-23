<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-10-22 (UTC) by pytest -q (785 passed, 5 skipped), statutor-doctor ., statutor staged .
last_worker: cursor
last_machine: unknown
handoff_id: c7d36125f7fd3765e236d3a4208f58d4
supersedes: b41b8ad341034c5c85c3756a1bb00974

## Goal
Close the 0.7.4 audit holes and add first-class Cursor support (D-0030).

## Last verified state
- Kernel: Antigravity relative TargetFile uses workspace CWD; truncated
  apply_patch denies; hook reports invalid HEAD policy; MultiEdit/
  NotebookEdit deny-unproved; matcher includes run_terminal_cmd.
- Stop/doctor/worker honor overwrite_bounded basename and empty-workspace
  silence. Rust missing optional OID key is None (s61).
- Cursor adapter: hook_event_name map, permission JSON fail-open,
  adapters/cursor/, dogfood .cursor/hooks.json, harness id cursor.
- Python/plugins 0.7.5, npm 0.2.0, crate 0.1.3. Publication is human.

## Next action
Human: review, then tag/publish v0.7.5 and crate 0.1.3. npm stays 0.2.0.

## Gotchas
- Cursor permission hooks fail-closed on exit 0 plus invalid JSON; the
  kernel always emits a permission object on a detected Cursor event.
- Hooks fail open; staged fails closed. Git hooks allow --no-verify.
- Do not reopen D-0028 empty-old_string Claude Edit, D-0015 bootstrap
  receipts, TASKS pruning, or research-note D-number relabel.

## Do not touch
Embedded templates/init profiles; frozen archive; DECISIONS.md header;
root pre-commit metadata. Preserve untracked .agents/, _local/, assets/,
notes/, and plans/v0.4-dogfood.pdf.
