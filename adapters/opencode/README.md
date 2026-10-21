# statutor × OpenCode

`statutor.ts` is one file with a default export that serves both plugin APIs:
`setup()` on OpenCode 2.x and `server()` on OpenCode 1.x
([1.18.29 or newer](https://opencode.ai/v2/docs/build/plugins/migrate-v1),
the first release with object entrypoints). Both register the same guard on
tool execution and shell out to the Python kernel CLI.

1. `pipx install 'statutor>=0.7.4'` — the adapter shells out to the kernel; without the
   CLI on `PATH` the plugin is a no-op. From a source checkout, the developer
   equivalent is `python -m pip install -e .` at the repository root.
   The adapter calls `statutor check --if-ledger`: it stays silent unless the
   nearest ancestor has `.statutor.yaml`, so a user-level installation does
   not impose Statutor's defaults on unrelated repositories.
2. Install the adapter itself:

   ```jsonc
   // OpenCode 2.x — opencode.json
   {
     "$schema": "https://opencode.ai/config.json",
     "plugins": ["statutor"]        // pin with "statutor@0.2.0"
   }
   ```

   ```jsonc
   // OpenCode 1.x — opencode.json
   {
     "$schema": "https://opencode.ai/config.json",
     "plugin": ["statutor"]         // pin with "statutor@0.2.0"
   }
   ```

   then restart opencode (config is read at startup).

   File-copy fallback, no npm needed: copy `statutor.ts` into
   `.opencode/plugins/` (project) or `~/.config/opencode/plugins/` (global),
   where OpenCode 2.x loads `.ts` files directly. A 2.x **config entry** must
   name a package or a directory; a bare `.ts` path is rejected with
   `configured plugin path must be a directory`.
3. Hook mapping — throwing blocks the tool call:

   | Host | Registration | Tool name / arguments |
   |---|---|---|
   | OpenCode 2.x | `ctx.tool.hook("execute.before", …)` | `event.tool`, `event.input` |
   | OpenCode 1.x | returned `"tool.execute.before"` hook | `input.tool`, `output.args` |

   The harness vocabulary changed in 2.x, so the adapter normalizes both
   generations to the kernel's names:

   | Kernel | OpenCode 1.x | OpenCode 2.x |
   |---|---|---|
   | `bash` | `bash` → `command` | `shell` → `command` |
   | `write` / `edit` | `filePath` | `path` |
   | `apply_patch` | `apply_patch` → `command` | `patch` → `patchText` |

   This matters more than the module shape: a plugin that loads cleanly but
   only knows the 1.x names silently guards nothing. A live 2.0.32 session
   confirmed the real ids (`shell`, `write`, `edit`, `patch`), and
   `tests/test_adapter_opencode.py` feeds those shapes through both
   registrations.

   The kernel's exit code 2 is the only denial signal. A missing CLI, a spawn
   failure, or an unparsable payload allows the call: hook mode fails open
   (the repository's kernel rule), so a broken adapter never bricks a session.
   The same test file covers the fail-open path. Verified 2026-10-20 against
   OpenCode 2.0.32 with live tool calls: a frozen `write` was denied, a
   `shell` redirect naming a governed file was denied, and an ordinary write
   passed. With no `.statutor.yaml` marker the guard stays silent.
4. Doctrine: OpenCode reads AGENTS.md natively — `statutor init` already covers
   the constitution. Optionally inject the condensed doctrine from
   `skills/statutor/SKILL.md` via the 2.x `ctx.session.hook("context", …)`
   (`event.system.push(...)`); on 1.x the same job used
   `experimental.chat.system.transform`.
5. Backstop: install the git floor (see adapters/git/). Not because of
   subagents — verified against opencode
   [v1.18.21](https://github.com/anomalyco/opencode/releases/tag/v1.18.21)
   (released 2026-08-21; checked 2026-08-23), subagent tool calls DO fire
   plugin hooks: the `task` tool spawns a child session that runs through
   the same prompt loop and the same plugin-wrapped tool set
   ([`session/tools.ts`](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/session/tools.ts#L107)).
   [sst/opencode#5894](https://github.com/anomalyco/opencode/issues/5894)
   was a misdiagnosis — the subagent had run grep/glob via the `bash`
   tool, so the hook correctly fired with `tool: "bash"` — and was closed
   by the stale bot on 2026-04-15, never by a fix. That check was made on the
   1.x hook surface; re-verify subagent coverage on 2.x before relying on it
   alone.

   The floor is still recommended for gaps the `tool.execute.before` /
   `execute.before` allowlist in `statutor.ts` cannot close:
   - MCP tools: their ids are server-namespaced, so name-based filtering
     never matches them.
   - Partial-diff blind spots: an apply_patch Update File's required
     sections cannot be verified from a partial diff, and its resulting
     line count is only estimated from the on-disk file plus adds-minus-
     dels — the floor judges the final staged blob exactly.
   - No agent identity: the 1.x hook input is only
     `{ tool, sessionID, callID }`, and the 2.x event adds `agent` and
     `messageID` but no primary/subagent role — correlate by `sessionID`
     instead.

   Patch tooling is covered in-loop: since T-0011 the kernel parses the
   `*** Begin Patch` envelope (frozen paths, Delete File of governed records,
   append-only deletions, and cap/sections on Add File). On 2.x that envelope
   arrives as the `patch` tool's `patchText`; the adapter maps it to the
   kernel's `apply_patch` shape.

## Optional global user layer (v0.4)

The global layer is separate from this npm enforcement adapter. It projects
the common constitution plus an OpenCode overlay to
`$XDG_CONFIG_HOME/opencode/AGENTS.md`. Skills are projected to the portable
`$HOME/.agents/skills` and Claude personal roots that OpenCode already
discovers; Statutor deliberately creates no third native OpenCode skill copy.
`statutor global status` and `doctor` explain native-vs-Claude instruction
fallback and classify duplicate skill trees as identical or divergent.

Use `statutor global init`, review `statutor global plan --json`, then opt in
with `statutor global apply --host opencode` and `statutor global skill apply`.
The separate `python scripts/global_e2e.py --host opencode --json` probe was
verified against local OpenCode 2.1.1. Under a temporary profile, its private
loopback API resolved the deliberately duplicated fixture to one skill entry
and preserved its body. The probe performs no model or external network
request and never points OpenCode at the caller's real home. Instruction
projections are verified on disk; model-context loading is not exercised.

## Worker provenance (v0.5)

`tool.execute.before` proves an **attempt** only — never a confirmed
mutation and never completion. Nothing is auto-recorded: the hook path
stays fail-open and fast, and the hook input carries no stable session
identity beyond `sessionID` (no primary/subagent distinction, so role
stays `unknown`). The ingress is executor- or custom-run:

- `statutor worker begin --harness opencode` at session start,
- `statutor worker record --harness opencode --event attempt --session <id>`
  from custom wiring only,
- rewrite the shift-change note with `last_worker`/`last_machine`, a fresh
  `handoff_id` superseding the baseline, then
  `statutor worker complete --session <id>`.

`statutor worker capabilities` reports the proven surfaces and gaps per
host; `statutor worker compare <ref>` explains sibling handoffs read-only.
Recording `--event mutation` under the `opencode` harness is denied by the
CLI — mutation requires a post-success surface no host currently proves.
