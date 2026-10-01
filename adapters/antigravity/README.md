# statutor × Google Antigravity

Statutor provides first-class, native support for **Google Antigravity** (AGY /
Gemini harness) alongside Claude Code, Codex, and OpenCode, with zero background
daemons and 100% fail-open hook safety.

## 1. Overview & Capabilities

| Layer | Antigravity Native Surface | Statutor Integration |
|---|---|---|
| **Constitution** | `AGENTS.md` (hierarchical walk to repo root) | Read directly; capped at soft 120 / hard 200 lines |
| **Pre-Mutation Hooks** | `PreToolUse` in `hooks.json` (`run_command`, `write_to_file`, `replace_file_content`) | Validates all 4 planes, bash guard, append policies |
| **Drift Monitoring** | `Stop` in `hooks.json` | Runs `statutor-doctor`; warns on drift, bounded to 1 continuation |
| **Procedures & Skills** | `skills/<name>/SKILL.md` (progressive disclosure) | Bundles 5 skills: `statutor`, `statutor-init`, `statutor-doctor`, `handoff`, `decide` |
| **Rules Projection** | `rules/AGENTS.md` in plugin bundle | Injects four-plane invariants into active agent context |
| **Worker Provenance** | `last_worker: antigravity` in `HANDOFF.md` | Machine-local session tracking (`statutor worker`) |
| **Absolute Backstop** | Pre-commit git hook | `statutor staged .` floor remains the unbypassable trust boundary |

## 2. Installation

Requires `statutor` on `PATH` (`pip install -e .` or `pipx install statutor`).

### Option A: Install as a Workspace Plugin (Recommended)

Copy or symlink this directory into your project's `.agents/plugins/` directory:

```bash
mkdir -p .agents/plugins
ln -s "$(pwd)/adapters/antigravity" .agents/plugins/statutor
```

Or declare it in `.agents/plugins.json`:

```json
{
  "entries": [
    { "path": "adapters/antigravity" }
  ]
}
```

### Option B: Install Globally

To enable Statutor across all projects on your workstation:

```bash
mkdir -p ~/.gemini/config/plugins
ln -s /path/to/statutor/adapters/antigravity ~/.gemini/config/plugins/statutor
```

### Option C: Direct Hook Integration

If you prefer using `.agents/hooks.json` directly without packaging as a plugin:

```json
{
  "statutor": {
    "PreToolUse": [
      {
        "matcher": "run_command|write_to_file|replace_file_content",
        "hooks": [
          {
            "type": "command",
            "command": "statutor hook",
            "timeout": 30
          }
        ]
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "statutor hook --stop",
        "timeout": 30
      }
    ]
  }
}
```

## 3. Tool Interception Details

Antigravity uses specific tools for filesystem and command operations. `statutor hook`
normalizes tool names and arguments:

*   **`run_command`** (`CommandLine`, `Cwd`):
    Mapped to `bash`. The strict bash scanner denies write-ish shell commands (`>`,
    `>>`, `sed -i`, `tee`, `cp`, `mv`) targeting governed filenames.
*   **`write_to_file`** (`TargetFile`, `CodeContent`, `Overwrite`, `Append`):
    Mapped to `write`.
    - `HANDOFF.md`: `Append: true` is denied (`overwrite_bounded` requires complete
      rewrite). `Overwrite: true` validates maximum 40 lines and required sections.
    - `DECISIONS.md`: `Append: true` is allowed as a pure insertion. Overwrites
      must contain existing records verbatim.
    - `AGENTS.md`: Total lines are verified against the 200-line hard cap.
    - `plans/archive/*`: All writes are denied (`frozen`).
*   **`replace_file_content`** (`TargetFile`, `TargetContent`, `ReplacementContent`, `AllowMultiple`):
    Mapped to `edit`.
    - `DECISIONS.md`: Edits must contain target content verbatim (append-only); modifying
      or deleting settled decisions is blocked.
    - `TASKS.md`: Task IDs (`T-NNNN`) cannot be deleted or renumbered; checkbox toggles
      and details are allowed.

## 4. Multi-Agent & Subagent Orchestration

Antigravity provides native subagents via `invoke_subagent`.

*   **Single-Writer Discipline**: The primary orchestrator maintains the ledger.
    Subagents write notes and scratch outputs to `notes/<task-id>.md` (or artifact
    files) and must never directly mutate governed files.
*   **Worker Attribution**:
    Start session tracking:
    ```bash
    statutor worker begin --harness antigravity
    ```
    On shift completion, update `HANDOFF.md`:
    ```markdown
    last_worker: antigravity
    last_machine: <machine-id>
    handoff_id: <random-id>
    supersedes: <baseline-id>
    ```
    Then record completion:
    ```bash
    statutor worker complete --session <session-id>
    ```
