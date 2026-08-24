# statutor × Codex CLI

Codex's hook surface mirrors Claude Code's protocol (stdin JSON in,
permissionDecision JSON / exit 2 out) — Codex's own source calls these
"Claude-style lifecycle hooks" — so the SAME kernel entry works:
`statutor hook`. Verified against Codex CLI
[rust-v0.149.0](https://github.com/openai/codex/releases/tag/rust-v0.149.0)
(npm `@openai/codex` 0.149.0, published 2026-08-20; checked 2026-08-23).
Three things to know:

1. Hooks are ON by default — no feature flag needed. `[features] hooks`
   has been `Stage::Stable, default_enabled: true` since
   [rust-v0.124.0](https://github.com/openai/codex/releases/tag/rust-v0.124.0)
   (2026-04-23); the old `[features] codex_hooks = true` is a deprecated
   legacy alias (key renamed in
   [rust-v0.129.0](https://github.com/openai/codex/releases/tag/rust-v0.129.0),
   2026-05-07) and setting it is now a no-op. What DOES gate hooks: a
   one-time trust prompt on first run (`/hooks` to review; approval
   persists as `[hooks.state.<key>] trusted_hash`, invalidated if the
   command string changes), and an admin can lock out all user/project
   hooks with `allow_managed_hooks_only = true` in requirements.toml.
2. PreToolUse fires for more than Bash — also `apply_patch` (matcher
   aliases `Write`/`Edit`), `spawn_agent` (alias `Agent`), MCP tools, and
   other local function tools; not for hosted tools like web search.
   Codex sends file edits as tool_name `apply_patch` with tool_input
   `{"command": "<apply_patch envelope text>"}` — not Claude's
   `{file_path, content}` — and matcher aliases deliberately don't change
   the payload seen by hook processes. Since T-0011, `validate()` in
   core/statutor_core.py parses that envelope (`guard_apply_patch`):
   frozen paths are untouchable (arrival INTO the archive still allowed),
   Delete File on a governed constitution/overwrite_bounded/append_only
   path is denied wholesale, Add File gets the full cap + required-sections
   check, and Update File denies append-only deletions and estimates the
   resulting line count. Residual blind spots — required sections on an
   Update File partial diff, and MCP tools — are covered by the GIT FLOOR
   (adapters/git/), which stays mandatory here.
3. Registration: BOTH `hooks.json` and an inline `[hooks]` table in
   config.toml are read, discovered per config layer (`~/.codex/` and
   `<repo>/.codex/`). Use exactly ONE per layer — a layer with both loads
   both and logs "prefer a single representation for this layer".

`~/.codex/hooks.json` (or `<repo>/.codex/hooks.json`):

    { "hooks": { "PreToolUse": [ { "matcher": "^Bash$",
        "hooks": [ { "type": "command", "command": "statutor hook",
        "timeout": 30, "statusMessage": "statutor policy check" } ] } ] } }

Equivalent inline form in config.toml (use instead of, never alongside,
hooks.json in the same layer):

    [[hooks.PreToolUse]]
    matcher = "^Bash$"
    [[hooks.PreToolUse.hooks]]
    type = "command"
    command = "statutor hook"
    timeout = 30
    statusMessage = "statutor policy check"

`matcher` is a regex over the tool name and its aliases. Since T-0011 the
kernel parses apply_patch envelopes, so widening to `"^(Bash|apply_patch)$"`
gives real in-loop file-mutation coverage; tools outside both patterns
(e.g. MCP ids) still never reach statutor — the git floor covers them.

Doctrine ports for free: Codex reads AGENTS.md natively (32 KiB combined
cap — another reason the constitution stays small; cap unverified in
this pass — the docs URL moved from developers.openai.com/codex/* to
learn.chatgpt.com/docs/*) and supports skills in the same
SKILL.md-with-frontmatter format; reuse skills/statutor/SKILL.md.
Commands: mirror commands/*.md as Codex custom prompts.
