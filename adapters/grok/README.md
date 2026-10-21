# statutor × Grok Build

Grok Build speaks the Claude hook protocol (snake_case `tool_name` /
`tool_input` / `cwd` / `stop_hook_active` on stdin, `permissionDecision`
JSON on stdout). The root plugin is the adapter. This directory is the
registration note, not a second plugin: installing both doubles every check.

`statutor hook` resolves the nearest `.statutor.yaml` marker and stays
silent outside an opted-in ledger. Inside one, policy comes from HEAD.
Requires `statutor` on `PATH` (`pipx install statutor` or `pip install -e .`)
unless the plugin command below is used, which calls the kernel by path.

## Install once

Plugin (skills, commands, and hooks together):

```bash
grok plugin marketplace add https://github.com/hoohugokim/statutor
grok plugin install statutor --trust
```

The repo root already has `hooks/hooks.json`, `skills/`, and `commands/`.
Grok reads `.claude-plugin/marketplace.json`. `CLAUDE_PLUGIN_ROOT` is set.

Or, with no plugin, one user hook file `~/.grok/hooks/statutor.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "^(Write|Edit|Bash|apply_patch|write|search_replace|hashline_edit|run_terminal_command|StrReplace|Shell)$",
        "hooks": [
          { "type": "command", "command": "statutor hook", "timeout": 30 }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "statutor hook --stop", "timeout": 30 }
        ]
      }
    ]
  }
}
```

The same matcher in `~/.grok/config.toml` (use instead of the JSON file in
that same layer, not beside it):

```toml
[[hooks.PreToolUse]]
matcher = "^(Write|Edit|Bash|apply_patch|write|search_replace|hashline_edit|run_terminal_command|StrReplace|Shell)$"
hooks = [
  { type = "command", command = "statutor hook", timeout = 30 },
]

[[hooks.Stop]]
hooks = [
  { type = "command", command = "statutor hook --stop", timeout = 30 },
]
```

The root plugin's Stop command is `hooks/stop_doctor.py`, not `statutor hook
--stop`. Both honor `stop_hook_active` and ignore a Stop whose `reason` is
present and not `end_turn` (Grok's session-end fire).

## What the kernel treats as a mutation

| Grok tool | Canonical | Body |
|---|---|---|
| `search_replace` | `edit` | `file_path`, `old_string`, `new_string`, `replace_all` |
| `write` | `write` | `file_path`, `content` |
| `run_terminal_command` (and `run_terminal_cmd`) | `bash` | `command` |
| `StrReplace` | `edit` | `path` is read as `file_path` |
| `Shell` | `bash` | `command` |
| `hashline_edit` with `old_string` | `edit` | same edit checks |
| `hashline_edit` without `old_string` | deny if the path is governed | the candidate cannot be reconstructed |

`contents` is read as `content`. A `toolInputTruncated` / `tool_input_truncated`
body denies a shell command inside a ledger, and denies a write or edit whose
path matches a governed rule. A truncated call to any other path stays silent.
Hook crashes still fail open.

## Worker provenance

Automatic hooks prove an attempt only and record nothing. Ingress:

```bash
statutor worker begin --harness grok
statutor worker record --harness grok --event attempt --session <id>
statutor worker complete --session <id>
```

`--event mutation` under `grok` is denied. `last_worker: grok` is a legal
HANDOFF id. Subagents (`spawn_subagent`) write `notes/<task-id>.md`. The
orchestrator owns the ledger. Subagent PreToolUse is not claimed until a
live probe sees one.

## Gaps the git floor still covers

- MCP calls dispatched as `server__tool` through `use_tool` never match the matcher.
- A bash-mode `!` command raises no PreToolUse.
- An unreconstructed `hashline_edit` of a governed file is denied rather than interpreted.

`statutor staged` remains the backstop. Do not add a `~/.grok/` global
projection while Claude compatibility is on: Grok already loads `~/.claude/`.
