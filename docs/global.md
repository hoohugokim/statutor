# Global instructions and skills

[Start here](../README.md) · [Architecture](architecture.md) · [Worker provenance](workers.md)

The optional global layer manages shared instructions and Agent Skills for
Claude Code, Codex, and OpenCode. It is separate from project-ledger
enforcement. Humans own the canonical sources; Statutor owns only complete
generated targets that it created or explicitly adopted.

## Set up shared instructions

```sh
statutor global init
statutor global plan --json
```

`init` creates canonical sources and versioned state without changing host
instruction files. Edit the common `AGENTS.md` and host overlays at the paths
reported by the plan. Review the resolved targets before applying one host:

```sh
statutor global apply --host codex
statutor global status --json
statutor global doctor --json
```

| Host | Instruction target |
|---|---|
| Claude Code | `$CLAUDE_CONFIG_DIR/CLAUDE.md`, normally `~/.claude/CLAUDE.md` |
| Codex | `$CODEX_HOME/AGENTS.md`, normally `~/.codex/AGENTS.md` |
| OpenCode | `$XDG_CONFIG_HOME/opencode/AGENTS.md`, normally `~/.config/opencode/AGENTS.md` |

An existing unmanaged target is a conflict. To import an existing Claude
instruction file into its host overlay with an original backup, explicitly
adopt it:

```sh
statutor global adopt claude
```

To remove managed projections and restore their original backups:

```sh
statutor global uninstall --host codex
```

Every mutation displays its resolved plan first. Writes check content tokens
and the recorded logical and resolved target identities. Managed hand edits
and retargeted parents cause refusal. Safe rollback restores the prior owned
artifact; external edits are preserved with recovery evidence. These checks
do not promise protection against adversarial directory replacement inside
operating-system calls. See [D-0018 and D-0029](../DECISIONS.md).

## Manage reusable skills

```sh
statutor global skill import ./my-skill
statutor global skill plan --json
statutor global skill apply
statutor global skill status --json
```

Import creates a new human-owned canonical skill source. Statutor validates
`SKILL.md` metadata and the complete tree while preserving host-specific
frontmatter. The source projects to `$HOME/.agents/skills` and Claude's
personal skills root. OpenCode discovers those projections; Statutor creates
no third OpenCode-native copy.

Edit the canonical source, then use `statutor global skill sync` to update
managed copies. `statutor global skill uninstall` restores their initial
backups. Identical unmanaged trees need explicit `--adopt-identical` on plan
and apply. Differing or hand-edited trees remain conflicts. Names in a foreign
`.agents/.skill-lock.json` remain foreign.

## Inspect ownership and precedence

`global status` is a fast, read-only inventory. It reports instruction
precedence, disabled or foreign skills, duplicate names, legacy/native/admin/
plugin roots, and catalog size. `global doctor` checks full trees for managed
drift, receipt topology, unsafe links, generated headers, and active divergent
duplicates. Its 32 KiB skill-description budget is a Statutor diagnostic,
not a host limit.

Status exits zero when inventory completes. Doctor exits one if it finds
errors. Neither command invokes host binaries or makes network requests.
Codex overrides and OpenCode's Claude fallback appear as precedence warnings;
Statutor does not rewrite host configuration, overrides, plugin/admin/system
content, or foreign locks.

Use `--home`, `--config-root`, and `--state-root` to select explicit isolated
roots for tests or alternate profiles. Real-home migration is an opt-in
operation, separate from testing.

## Run the native host probe

From a source checkout with the tested host binaries installed:

```sh
python scripts/global_e2e.py --json
```

The probe rehomes hosts under a temporary profile and never mutates the
caller's real home. It makes no model or external network request. OpenCode
uses a private loopback server. The probe checks modified-target refusal,
uninstall recovery, and native discovery where an offline command exists.

Verified global-layer baselines are Claude Code 2.1.296, Codex CLI 0.162.1,
and OpenCode 2.1.1. Codex exposes its prompt catalog; OpenCode exposes a skill
catalog. Claude has no offline personal-skill catalog probe. OpenCode
instruction projections are checked on disk, without exercising model-context
loading. These results do not expand [worker capability claims](workers.md).
