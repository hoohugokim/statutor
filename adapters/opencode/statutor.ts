// statutor adapter for OpenCode — one file, both plugin APIs.
//   OpenCode 2.x:  "plugins": ["statutor"]        (default export, setup)
//   OpenCode 1.x:  "plugin":  ["statutor"]        (default export, server;
//                                                  requires 1.18.29 or newer)
// or copy this file into .opencode/plugins/. Requires the statutor CLI on
// PATH (pipx install statutor, or pip install -e .); without it the guard
// stays silent.
//
// The guard calls `statutor check --if-ledger`: it does nothing unless the
// nearest ancestor carries `.statutor.yaml`, so a user-level install never
// imposes defaults on unrelated repositories. Exit code 2 is a denial and
// throwing blocks the tool call; every other outcome (missing CLI, spawn
// failure, unparsable payload) allows it — hook mode fails open.
//
// Hook mapping: v1 `tool.execute.before` receives `(input, output)` with the
// tool arguments under `output.args`; v2 registers `ctx.tool.hook(
// "execute.before")` and receives one event with the arguments under
// `event.input`. Both funnel into `guard()` below.
//
// Harness vocabulary differs from the kernel's and changed in 2.x:
//   bash (v1) / shell (v2)          -> command
//   write, edit (both)              -> filePath (v1) / path (v2)
//   apply_patch (v1) / patch (v2)   -> command / patchText envelope
// `normalize()` maps each shape to the kernel's canonical one; the kernel
// still owns policy semantics. Subagent tool calls DO fire plugin hooks
// (verified on the 1.x hook surface, opencode v1.18.21, 2026-08-21;
// sst/opencode#5894 was a misdiagnosis, stale-closed 2026-04-15). The
// remaining gap is server-namespaced MCP tool ids — the git floor covers
// them. See adapters/opencode/README.md.
import { spawn } from "node:child_process"

const GUARDED: Record<string, string> = {
  bash: "bash",
  shell: "bash",
  write: "write",
  edit: "edit",
  patch: "apply_patch",
  apply_patch: "apply_patch",
}

interface HookEvent {
  tool?: string
  input?: unknown
}

interface V2Context {
  location: { directory: string }
  tool: {
    hook(
      name: "execute.before",
      handler: (event: HookEvent) => Promise<void>,
    ): Promise<unknown>
  }
}

interface V1Context {
  directory: string
}

interface V1Hooks {
  "tool.execute.before": (
    input: { tool?: string } | undefined,
    output: { args?: unknown } | undefined,
  ) => Promise<void>
}

interface CheckResult {
  code: number
  stderr: string
}

function encode(input: unknown): string {
  try {
    return JSON.stringify(input ?? {})
  } catch {
    return "{}"
  }
}

function normalize(tool: string, input: unknown): Record<string, unknown> {
  const payload: Record<string, unknown> =
    input !== null && typeof input === "object"
      ? { ...(input as Record<string, unknown>) }
      : {}
  if (tool === "bash" || tool === "shell") {
    return { command: payload.command ?? "" }
  }
  if (tool === "write" || tool === "edit") {
    const path = payload.path ?? payload.filePath ?? payload.file_path
    if (path !== undefined && payload.file_path === undefined) {
      payload.file_path = path
    }
    if (payload.replaceAll !== undefined && payload.replace_all === undefined) {
      payload.replace_all = payload.replaceAll
    }
    return payload
  }
  if (tool === "patch" || tool === "apply_patch") {
    const text = payload.patchText ?? payload.patch ?? payload.command
    return { command: typeof text === "string" ? text : "" }
  }
  return payload
}

function runCheck(tool: string, input: unknown, directory: string): Promise<CheckResult> {
  return new Promise((resolve) => {
    let settled = false
    const settle = (result: CheckResult) => {
      if (settled) return
      settled = true
      resolve(result)
    }
    let child: ReturnType<typeof spawn>
    try {
      child = spawn(
        "statutor",
        ["check", "--if-ledger", tool, encode(input), directory],
        { stdio: ["ignore", "ignore", "pipe"] },
      )
    } catch {
      settle({ code: 0, stderr: "" })
      return
    }
    let stderr = ""
    child.stderr?.on("data", (chunk: unknown) => {
      stderr += String(chunk)
    })
    child.on("error", () => settle({ code: 0, stderr: "" }))
    child.on("close", (code) => settle({ code: code ?? 0, stderr }))
  })
}

async function guard(tool: string, input: unknown, directory: string): Promise<void> {
  const name = (tool ?? "").toLowerCase()
  const canonical = GUARDED[name]
  if (canonical === undefined) return
  const { code, stderr } = await runCheck(canonical, normalize(name, input), directory)
  if (code === 2) {
    throw new Error(stderr.trim() || "[statutor] blocked by ledger policy")
  }
}

const plugin = {
  id: "statutor",
  async setup(ctx: V2Context): Promise<void> {
    await ctx.tool.hook("execute.before", async (event) => {
      await guard(String(event.tool ?? ""), event.input, ctx.location.directory)
    })
  },
  async server(ctx: V1Context): Promise<V1Hooks> {
    return {
      "tool.execute.before": async (input, output) => {
        await guard(String(input?.tool ?? ""), output?.args, ctx.directory)
      },
    }
  },
}

export default plugin
