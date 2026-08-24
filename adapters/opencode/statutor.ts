// statutor adapter for OpenCode — copy into .opencode/plugins/ (or your plugin dir).
// Requires the statutor CLI on PATH (pipx install statutor, or pip install -e .).
// tool.execute.before ~ Claude Code's PreToolUse: throwing blocks the call.
// Subagent tool calls DO fire plugin hooks (verified opencode v1.18.21,
// 2026-08-21; sst/opencode#5894 was a misdiagnosis, stale-closed 2026-04-15).
// The real gaps this allowlist can't close: apply_patch (opencode substitutes
// it for write/edit on GPT-5-class models) and server-namespaced MCP tool
// ids — the git floor covers both. See adapters/opencode/README.md.
import type { Plugin } from "@opencode-ai/plugin"

export const Statutor: Plugin = async ({ $, directory }) => ({
  "tool.execute.before": async (input, output) => {
    const tool = (input?.tool ?? "").toLowerCase()
    if (!["write", "edit", "bash"].includes(tool)) return
    const args = JSON.stringify(output?.args ?? {})
    const r = await $`statutor check ${tool} ${args} ${directory}`.quiet().nothrow()
    if (r.exitCode === 2) throw new Error(r.stderr.toString() || "[statutor] blocked by ledger policy")
  },
})
