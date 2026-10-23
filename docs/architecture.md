# Architecture and enforcement

[Start here](../README.md) · [Ledger rules](policy.md) · [Global instructions](global.md) · [Worker provenance](workers.md)

The canonical Python kernel validates proposed file changes. Adapters translate
agent tool events into that shared contract. The staged validator checks the
complete Git index independently of which tool produced it.

## Components

| Component | Responsibility |
|---|---|
| [`core/statutor_core.py`](../core/statutor_core.py) | `validate()`, embedded templates and init profiles, policy parsing, hook/check/staged/init/trust commands. No third-party dependencies. |
| [`core/statutor_doctor.py`](../core/statutor_doctor.py) | Drift diagnostics for dates, budgets, state records, and consumed plans. |
| [`hooks/stop_doctor.py`](../hooks/stop_doctor.py) | Non-blocking drift feedback at the end of an agent turn. |
| [`core/statutor_global.py`](../core/statutor_global.py) | Global roots, schemas, hashes, target identity, atomic replacement, backups, and recovery. |
| [`core/statutor_global_cli.py`](../core/statutor_global_cli.py) | Opt-in global instruction planning, adoption, apply, and uninstall. |
| [`core/statutor_skills.py`](../core/statutor_skills.py) | Agent Skill validation and complete-tree projections. |
| [`core/statutor_global_status.py`](../core/statutor_global_status.py) | Global inventory, precedence, ownership, and deeper doctor diagnostics. |
| [`core/statutor_worker.py`](../core/statutor_worker.py) | Machine-local worker evidence, session identity, and HANDOFF lineage checks. |
| [`crates/statutor/`](../crates/statutor/README.md) | Native staged-index implementation, conformance-gated against Python. |

Templates live only in the kernel. The package exposes the `statutor` and
`statutor-doctor` console scripts. PyYAML is optional; enforcement does not
require it.

## Enforcement layers

| Layer | Input | Failure behavior |
|---|---|---|
| Automatic hook | A supported pre-tool event in a marked ledger | Denies known policy violations; fails open on an internal hook error. |
| Explicit `statutor check` | A tool name, JSON payload, and directory | Exit 2 reports a policy denial. |
| `statutor staged` | HEAD and the current worktree's staged index | Fails closed on invalid policy or Git read errors. |
| `statutor-doctor` | Ledger files and policy | Reports drift without mutating files. |

Automatic adapters stay silent outside the nearest `.statutor.yaml` ledger.
Explicit checks can be used by custom integrations. The
[policy guide](policy.md) explains committed-policy authority and bootstrap.

## Agent adapters

The root of this repository is the Claude Code plugin. Grok Build uses the
same hook protocol and plugin with its own tool vocabulary. Cursor uses
`hooks.json` v1 (`preToolUse`, `beforeShellExecution`, `beforeMCPExecution`,
`stop`) and Cursor permission JSON. OpenCode uses a TypeScript adapter with
2.x `setup()` and 1.x `server()` entrypoints. Codex uses the shared hook
command for shell and `apply_patch` events. Antigravity normalizes native
tool arguments, including batch replacements.

Use each adapter guide for registration and exact coverage:
[Codex](../adapters/codex/README.md),
[OpenCode](../adapters/opencode/README.md),
[Antigravity](../adapters/antigravity/README.md),
[Grok Build](../adapters/grok/README.md), and
[Cursor](../adapters/cursor/README.md).

Hook coverage varies by host. Server-namespaced MCP tool IDs and required
sections in partial Update File patches are known gaps. The floor judges the
final staged blob, including its exact line count and required sections.
Historical OpenCode subagent coverage was verified on 1.x; that result does
not prove 2.x subagent coverage. Stop feedback reports drift, not completion.

## Custom integrations

Call the CLI before a proposed write. Exit 2 means the integration must deny it:

```sh
statutor check --if-ledger write '{"file_path":"notes/example.md","content":"example"}' .
```

For an application that installs the Python package in its own environment,
call `validate()` with the tool name, complete payload, and project directory:

```python
from statutor_core import validate

reason = validate("write", {"file_path": "notes/example.md", "content": "example"}, cwd=".")
if reason is not None:
    raise ValueError(reason)
```

`validate()` returns a denial reason or `None`. The caller performs the actual
write only after validation succeeds. It does not register hooks or write files.

## Local Git floor

The [Git adapter](../adapters/git/README.md) runs `statutor staged` in local
pre-commit and CI checks. The native `statutor-staged` binary implements the
same local staged-index contract without requiring Python. It is not a
server-side pre-receive validator and does not promise fully static linkage.
`--no-verify` remains an explicit unverified escape from a local commit hook.

Tests compare expected verdicts and Python/Rust output. The
[release gate](releasing.md) also audits real package contents and smoke-tests
an installed wheel from an isolated candidate snapshot.

## Design references

The name comes from the agent noun of *statuere*, one who enacts. The design
draws on the [AGENTS.md standard](https://agents.md/),
[Claude memory](https://code.claude.com/docs/en/memory) and
[hooks](https://code.claude.com/docs/en/hooks), Anthropic's
[long-running agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
and [context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents),
[MADR](https://adr.github.io/madr/),
[Keep a Changelog](https://keepachangelog.com/),
[Conventional Commits](https://www.conventionalcommits.org/), and
[pre-commit](https://pre-commit.com/).
