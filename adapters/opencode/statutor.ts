// statutor adapter for OpenCode — install via opencode.json:
//   "plugin": ["statutor"]
// (or copy this file into .opencode/plugins/). Requires the statutor CLI
// on PATH (pipx install statutor, or pip install -e .).
// tool.execute.before ~ Claude Code's PreToolUse: throwing blocks the call.
// Subagent tool calls DO fire plugin hooks (verified opencode v1.18.21,
// 2026-08-21; sst/opencode#5894 was a misdiagnosis, stale-closed 2026-04-15).
// The allowlist includes apply_patch (opencode substitutes it for write/edit
// on GPT-5-class models): the kernel parses its *** Begin Patch envelope.
// Remaining gap: server-namespaced MCP tool ids — the git floor covers them.
// See adapters/opencode/README.md.
import type { Plugin } from "@opencode-ai/plugin"

export const Statutor: Plugin = async ({ $, directory }) => ({
  "tool.execute.before": async (input, output) => {
    const tool = (input?.tool ?? "").toLowerCase()
    if (!["write", "edit", "bash", "apply_patch"].includes(tool)) return
    const args = JSON.stringify(output?.args ?? {})
    const r = await $`statutor check ${tool} ${args} ${directory}`.quiet().nothrow()
    if (r.exitCode === 2) throw new Error(r.stderr.toString() || "[statutor] blocked by ledger policy")
  },
})
