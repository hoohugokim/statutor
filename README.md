<p align="center">
  <img src="https://raw.githubusercontent.com/hoohugokim/statutor/main/docs/branding/statutor-mark.svg" width="72" height="72" alt="">
</p>

<h1 align="center">Statutor</h1>

<p align="center"><strong>Keep project rules, handoffs, and decisions intact across coding-agent sessions.</strong></p>

<p align="center">
  <a href="https://github.com/hoohugokim/statutor/actions/workflows/ci.yml"><img src="https://github.com/hoohugokim/statutor/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status"></a>
  <a href="https://pypi.org/project/statutor/"><img src="https://img.shields.io/pypi/v/statutor?color=1745be" alt="PyPI version"></a>
  <a href="https://github.com/hoohugokim/statutor/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-6b7280" alt="MIT license"></a>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> · <a href="#choose-your-agent">Agents</a> · <a href="#how-the-ledger-works">The ledger</a> · <a href="#documentation">Documentation</a>
</p>

Statutor gives a repository a small set of files for its rules, current work,
and decision history. Hooks check supported tool calls before they write.
The Git check validates the staged result against the committed policy.

```text
Append a new decision         → allowed
Rewrite an earlier decision  → blocked
Edit an ordinary source file → allowed
```

## Quickstart

### Install and initialize

Requires Python 3.10 or later. Run these commands in your project directory:

```sh
pipx install statutor
statutor init .
```

Existing files stay unchanged. `init` creates the ledger and detects a small
project profile. Use `statutor init . --type none` for governed files only.
[Profiles and policy](https://github.com/hoohugokim/statutor/blob/main/docs/policy.md).

### Choose your agent

Connect an adapter to check supported tool calls during a session. Installing
the CLI and initializing a ledger do not register agent hooks.

| Agent | In-loop checks | Setup |
|---|---|---|
| Claude Code | File edits, shell, and patches | [Plugin commands below](#claude-code) |
| Codex CLI | Shell and patches | [Guide](https://github.com/hoohugokim/statutor/blob/main/adapters/codex/README.md) |
| OpenCode | File edits, shell, and patches | [Guide](https://github.com/hoohugokim/statutor/blob/main/adapters/opencode/README.md) |
| Google Antigravity | File edits, batch edits, and shell | [Guide](https://github.com/hoohugokim/statutor/blob/main/adapters/antigravity/README.md) |
| Grok Build | File edits and shell | [Guide](https://github.com/hoohugokim/statutor/blob/main/adapters/grok/README.md) |
| Custom agents | Checks through the CLI or Python API | [API and architecture](https://github.com/hoohugokim/statutor/blob/main/docs/architecture.md) |

#### Claude Code

Run these slash commands inside Claude Code:

```text
/plugin marketplace add https://github.com/hoohugokim/statutor
/plugin install statutor@hoo-plugins --scope project
```

The repository is the plugin. It includes `/statutor-init`, `/handoff`,
`/decide`, and `/statutor-doctor`.

### Enable the Git backstop

Hooks cover different tools on each agent. Use the staged-index check in
addition to your agent adapter. With [pre-commit](https://pre-commit.com/#installation)
installed, add this entry to your project's `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/hoohugokim/statutor
    rev: v0.7.4
    hooks: [{id: statutor}]
```

Then install the Git hook and check the ledger:

```sh
pre-commit install
statutor-doctor .
```

Run `statutor staged .` to check the current index directly. A
[native Rust binary](https://github.com/hoohugokim/statutor/blob/main/crates/statutor/README.md)
provides the same staged checks without Python.
[Git setup and limits](https://github.com/hoohugokim/statutor/blob/main/adapters/git/README.md).

## How the ledger works

Each file has a designated writer and a mutation policy. Four planes separate
rules, current state, decisions, and plans:

| Plane | Default files | Rule |
|---|---|---|
| Constitution | `AGENTS.md` | Human-owned rules, capped at 200 lines |
| State | `HANDOFF.md`, `TASKS.md` | Bounded handoff; stable task IDs |
| Log | `DECISIONS.md` | Append new decisions; preserve earlier entries |
| Plan | `ROADMAP.md`, `plans/` | Archived plans are frozen |

The default handoff is limited to 40 lines. Task checkboxes, descriptions, and
ordering can change; existing IDs remain. `CLAUDE.md` bridges to `AGENTS.md`.
See [policy and trust](https://github.com/hoohugokim/statutor/blob/main/docs/policy.md)
for writer roles, budgets, shell checks, and intentional policy changes.

## Optional capabilities

- [Global instructions and skills](https://github.com/hoohugokim/statutor/blob/main/docs/global.md):
  preview and manage shared instructions and skills across supported hosts.
  This is a separate opt-in operation from project initialization.
- [Worker provenance](https://github.com/hoohugokim/statutor/blob/main/docs/workers.md):
  record sessions and attributed handoffs. Automatic hooks prove attempts,
  never successful mutation, and record nothing by themselves.

## Coverage and limits

Automatic adapters stay silent outside a repository explicitly marked
by `.statutor.yaml`. Hook failures allow the session to continue. The staged
floor fails closed on invalid policy or Git errors. It inspects the local
index; Git hooks can be bypassed with `--no-verify`.

MCP tools and some partial-patch checks remain outside in-loop coverage.
Use the Git backstop to check their staged results. Agent-specific guides
above describe each adapter's scope and verified behavior.

## Documentation

[Policy and trust](https://github.com/hoohugokim/statutor/blob/main/docs/policy.md) ·
[Architecture and API](https://github.com/hoohugokim/statutor/blob/main/docs/architecture.md) ·
[Global layer](https://github.com/hoohugokim/statutor/blob/main/docs/global.md) ·
[Workers](https://github.com/hoohugokim/statutor/blob/main/docs/workers.md) ·
[Releasing](https://github.com/hoohugokim/statutor/blob/main/docs/releasing.md) ·
[Release notes](https://github.com/hoohugokim/statutor/releases)

For local development, run `pip install -e .`, `pytest -q`, and
`statutor-doctor .`. The kernel has no third-party dependencies; PyYAML is
optional. [Architecture](https://github.com/hoohugokim/statutor/blob/main/docs/architecture.md)
covers the source layout, validation modes, design references, and contribution checks.
