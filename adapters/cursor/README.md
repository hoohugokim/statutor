# statutor × Cursor

Cursor hooks use a version-1 `hooks.json` file and JSON over stdin/stdout.
`statutor hook` auto-detects `hook_event_name` and returns Cursor
`permission` JSON. Claude nested `hookSpecificOutput` still works for
`preToolUse` because Cursor accepts that shape too.

The kernel first resolves the nearest `.statutor.yaml` marker. Permission
events outside an opted-in ledger return `allow` without policy checks or
messages. Inside a ledger, policy comes from HEAD.
Requires Statutor **0.7.5 or newer** on `PATH`. Check `statutor version` before
enabling the hooks; earlier versions do not support Cursor hooks.

## Install once

Install or upgrade the CLI with `pipx install 'statutor>=0.7.5'` or
`pipx upgrade statutor`. While 0.7.5 is still a candidate, install it from a
local Statutor checkout with `pip install -e /absolute/path/to/statutor`.

From your ledger repository, copy [hooks.json](hooks.json) from that
Statutor checkout. Replace the absolute source path below with your own:

```sh
mkdir -p .cursor
cp /absolute/path/to/statutor/adapters/cursor/hooks.json .cursor/hooks.json
```

If `.cursor/hooks.json` already exists, merge the four events instead of
replacing it. Project hooks run from the repository root. This Statutor
repository already dogfoods `.cursor/hooks.json` against
`core/statutor_core.py`, so this checkout works without a global CLI.

Do not set `failClosed`. Hook crashes and missing CLI must fail open.
Invalid JSON on exit 0 would block Cursor permission events, so the kernel
always emits a permission object on a detected Cursor event.

The Stop hook reports ledger drift through Cursor's native
[`followup_message`](https://cursor.com/docs/hooks#stop). It requests at most
one follow-up per completion chain; a repeated Stop, an aborted or failed
run, and a clean ledger stay quiet.

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
An empty workspace list is allowed without policy checks. Stop stays quiet
without a ledger workspace.

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
