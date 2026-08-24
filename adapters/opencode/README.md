# statutor × OpenCode

1. `pipx install statutor` (or `pip install -e <statutor checkout>`).
2. Copy `statutor.ts` into your project's OpenCode plugin directory.
3. Doctrine: OpenCode reads AGENTS.md natively — `statutor init` already covers
   the constitution. Optionally inject the condensed doctrine from
   `skills/statutor/SKILL.md` via the `experimental.chat.system.transform` hook.
4. Backstop: install the git floor (see adapters/git/). Not because of
   subagents — verified against opencode
   [v1.18.21](https://github.com/anomalyco/opencode/releases/tag/v1.18.21)
   (released 2026-08-21; checked 2026-08-23), subagent tool calls DO fire
   plugin hooks: the `task` tool spawns a child session that runs through
   the same prompt loop and the same plugin-wrapped tool set
   ([`session/tools.ts`](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/session/tools.ts#L107)).
   [sst/opencode#5894](https://github.com/anomalyco/opencode/issues/5894)
   was a misdiagnosis — the subagent had run grep/glob via the `bash`
   tool, so the hook correctly fired with `tool: "bash"` — and was closed
   by the stale bot on 2026-04-15, never by a fix.

   The floor is still recommended for gaps the `tool.execute.before`
   allowlist in `statutor.ts` cannot close:
   - MCP tools: their ids are server-namespaced, so name-based filtering
     never matches them.
   - Partial-diff blind spots: an apply_patch Update File's required
     sections cannot be verified from a partial diff, and its resulting
     line count is only estimated from the on-disk file plus adds-minus-
     dels — the floor judges the final staged blob exactly.
   - No agent identity: the hook input is only
     `{ tool, sessionID, callID }` — a plugin can't tell primary agent
     from subagent, only correlate by `sessionID`.

   `apply_patch` itself is covered in-loop since T-0011: the allowlist
   includes it and the kernel parses the `*** Begin Patch` envelope
   (frozen paths, Delete File of governed records, append-only deletions,
   and cap/sections on Add File).
