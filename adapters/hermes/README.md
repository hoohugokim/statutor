# statutor × Hermes Agent

Verified against the local hermes-agent checkout (`~/.hermes/hermes-agent`,
2026-08-24). Two integration surfaces exist; both are usable, so T-0010's
"git-floor-only until a hook surface is confirmed" resolves to **full
in-loop enforcement**.

## 1. Enforcement — the plugin adapter (confirmed hook surface)

Hermes plugins are Python modules registered from `~/.hermes/plugins/`
whose `register(ctx)` calls `ctx.register_hook(...)`. The `pre_tool_call`
hook receives `{tool_name, args, task_id, session_id, ...}` and can veto:

    {"action": "block", "message": "..."}   # message becomes the tool result

(`hermes_cli/plugins.py` → `_get_pre_tool_call_directive_details`; the
block path fires in `agent/tool_executor.py` via
`_dispatch_pre_tool_call_hooks`. An `approve` directive escalates to the
human-approval gate; we don't use it.)

Tool mapping (schema names verified in `tools/file_tools.py`,
`tools/terminal_tool.py`):

| Hermes tool | args | kernel call |
|---|---|---|
| `write_file` | `{path, content}` | `validate("write", …)` |
| `patch` mode=replace | `{path, old_string, new_string}` | `validate("edit", …)` |
| `patch` mode=patch | `{patch}` (V4A envelope) | `validate("apply_patch", …)` |
| `terminal` | `{command}` | `validate("bash", …)` |

Install:

    mkdir -p ~/.hermes/plugins/statutor
    cp adapters/hermes/statutor-plugin/{plugin.yaml,__init__.py} ~/.hermes/plugins/statutor/
    pip install statutor   # into the interpreter Hermes actually runs

Kernel resolution order: importable `statutor_core` module → `$STATUTOR_KERNEL`
path → a sibling copy of `statutor_core.py` (forks the kernel; drift risk).
Fail-open: no kernel found means the plugin silently does nothing and the
git floor carries enforcement.

Caveat: hooks see the daemon's `os.getcwd()`, not per-command cwd — a
session that works deep inside subdirs still resolves governed basenames
correctly (fnmatch matches at any depth), but relative frozen-pattern
paths assume the session root. The git floor catches anything that slips
past.

## 2. Doctrine — skills (agentskills.io format)

`~/.hermes/skills/` uses `<group>/<skill-name>/SKILL.md` with agentskills.io
frontmatter (`name`, `description`, plus Hermes extras like `version`,
`platforms`). Our `skills/statutor/SKILL.md` is already spec-shaped, so
doctrine ports verbatim:

    mkdir -p ~/.hermes/skills/statutor
    cp -r skills/statutor ~/.hermes/skills/statutor/

Skills are advisory only (progressive disclosure, no enforcement) — pair
them with the plugin above or the git floor.
