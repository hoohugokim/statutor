# statutor × Cursor

Cursor hooks use a version-1 `hooks.json` file and JSON over stdin/stdout.
`statutor hook` auto-detects `hook_event_name` and returns Cursor
`permission` JSON. Claude nested `hookSpecificOutput` still works for
`preToolUse` because Cursor accepts that shape too.

The kernel first resolves the nearest `.statutor.yaml` marker and stays
silent outside an opted-in ledger. Inside one, policy comes from HEAD.
Requires `statutor` on `PATH` (`pipx install statutor` or `pip install -e .`)
unless the project file below calls the kernel by path.

## Install once

Copy [hooks.json](hooks.json) to `.cursor/hooks.json` in the ledger
repository, or merge the four events into an existing file. Project hooks
run from the repository root.

```sh
mkdir -p .cursor
cp adapters/cursor/hooks.json .cursor/hooks.json
```

This Statutor repository already dogfoods `.cursor/hooks.json` against
`core/statutor_core.py` so a checkout works without a global CLI.

Do not set `failClosed`. Hook crashes and missing CLI must fail open.
Invalid JSON on exit 0 would block Cursor permission events, so the kernel
always emits a permission object on a detected Cursor event.

## What the kernel treats as a mutation

| Cursor event | Canonical | Body |
|---|---|---|
| `preToolUse` `Write` | `write` | `path` / `contents` |
| `preToolUse` `StrReplace` | `edit` | `path`, `old_string`, `new_string` |
| `preToolUse` `Shell` | `bash` | `command` |
| `preToolUse` `Delete` | deny if governed | `path` |
| `preToolUse` `MultiEdit` / `NotebookEdit` | deny-unproved if governed | `path` / `file_path` |
| `beforeShellExecution` | `bash` | top-level `command` |
| `beforeMCPExecution` | mapped tool, else bash if `command` | `tool_input` JSON string |

`workspace_roots[0]` is the ledger search root when `cwd` is absent.
An empty workspace list stays silent.

## Worker provenance

Stable harness id is `cursor`. Automatic hooks prove an attempt only.

```bash
statutor worker begin --harness cursor
statutor worker complete --session <id>
```

`--event mutation` under `cursor` is denied.

## Gaps the git floor still covers

- MCP tools whose payload cannot be mapped to write/edit/bash.
- Tab completions (`afterTabFileEdit`) are post-hoc; use `statutor staged`.
- Local Git hooks can be skipped with `--no-verify`.
