# Ledger rules and policy

[Start here](../README.md) · [Architecture](architecture.md) · [Worker provenance](workers.md)

Use this guide when changing ledger rules, choosing an initialization profile,
or approving a policy change. The default ledger separates four kinds of record.

| Plane | Default files | Writer | Rule |
|---|---|---|---|
| Constitution | `AGENTS.md` | Human | Keep the shared instructions within the configured line budget. |
| State | `HANDOFF.md` | Executor | Replace the shift-change note; preserve its required sections and line cap. |
| State | `TASKS.md` | Orchestrator | Preserve task IDs while updating status, detail, and order. |
| Log | `DECISIONS.md` | Decision recorder | Add records; supersede earlier decisions with new records. |
| Plan | `ROADMAP.md`, `plans/` | Human | Keep the active plan separate from the frozen archive. |

The default hard cap is 200 physical lines for `AGENTS.md` and 40 for
`HANDOFF.md`. `CLAUDE.md` contains `@AGENTS.md` as a compatibility bridge.
The committed `.statutor.yaml` defines each project's actual filenames and rules.

## Initialize a project

```sh
statutor init .
```

Initialization creates missing ledger files and skips existing paths. It never
overwrites or adopts an existing constitution, policy, or `CLAUDE.md`, and it
does not follow existing paths while creating the scaffold.

Profiles add empty conventional directories. Selection follows this order:
`--type NAME`, then `STATUTOR_INIT_TYPE`, then the first detected marker in
the table below, then `min`.

| Profile | Additional directories | Detection markers |
|---|---|---|
| `python` | `tests/` | `pyproject.toml`, `setup.py`, `setup.cfg` |
| `rust` | `tests/` | `Cargo.toml` |
| `node` | `test/` | `package.json` |
| `docs` | `docs/` | `mkdocs.yml`, `_quarto.yml`, existing `docs/` |
| `min` | None beyond `plans/archive/` and `notes/` | Fallback or explicit selection |
| `none` | None, including no `plans/archive/` or `notes/` | Explicit selection only |

```sh
statutor init . --type none
```

Profiles do not impose a project layout or write ecosystem configuration.
The profile decision is [D-0024 in the decision log](../DECISIONS.md).

## Preserve record identity

Each task occupies one line, such as `- [ ] T-0001 Describe the work`.
IDs have at least four decimal digits and must be unique. An existing ID
cannot disappear or be renamed. Its checkbox, detail, and position may change.
New IDs must exceed the committed maximum. Completed tasks remain in place;
there is no pruning operation. [D-0016](../DECISIONS.md) defines this contract.

For append-only records, committed lines remain byte-identical and in order.
Add a new decision to supersede an earlier one. Frozen archive files cannot
be edited, deleted, or added directly. Move an existing plan into
`plans/archive/` to archive it.

## Use editor tools for governed files

The shell guard denies write commands targeting governed files, including
redirects, `sed -i`, and `tee`. Editor tools give Statutor the proposed content
to validate. The Git floor checks the complete staged result afterward.

A complete quoted heredoc used as `git commit -F -` message data is excluded
from shell-code scanning. Its opener and actual command lines remain guarded.
Quoted text, notes, and tool output provide context; they do not authorize a
mutation. See [D-0019](../DECISIONS.md) for the shell-message exception.

## Change policy with explicit approval

In-loop checks use the committed HEAD policy. The Git floor judges a staged
transaction under both the HEAD policy and the candidate index policy.
Unstaged or co-staged weakening cannot disable the existing rules.

The policy format is a strict, zero-dependency YAML subset shared by Python
and Rust. Malformed or unsupported policy and Git read failures deny at the
floor. Before the marker's first commit, automatic hooks use embedded defaults.
An edited worktree policy becomes hook authority only after it is committed.

After bootstrap, changes to `.statutor.yaml` or Statutor's exact
`CLAUDE.md` bridge require an exact-tree Git-local approval receipt:

```sh
git add .statutor.yaml
statutor trust approve . --decision D-0015 --reason "why this changes trust"
statutor staged .
```

Use the decision ID that records your own project's change. Approval displays
the reserved diff and every staged path, then requires the full candidate
tree ID. The mode-0600 receipt is never committed and expires if HEAD or any
staged entry changes, including a Git mode change.

Approval permits the trust-root transition; it does not relax the old policy
for another ledger mutation in the same commit. Commit an approved weakening
first, then make the newly permitted change separately. Receipts record
authorization, not human authentication. Local hooks can still be bypassed
with `--no-verify`. See [D-0015 and D-0029](../DECISIONS.md) and the
[Git adapter](../adapters/git/README.md).
