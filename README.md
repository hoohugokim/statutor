# statutor

Typed project-ledger framework for agentic repos. A *statutor* is one who
enacts (agent noun of *statuere*) — which is the thesis: repo instruction
files are a state machine of typed registers, each with a mutation policy
and exactly one writer, enforced by hooks and git, not by prose.

| Plane | Files | Policy | Enforced by |
|---|---|---|---|
| Constitution | AGENTS.md (+ CLAUDE.md = `@AGENTS.md`) | hard cap 200 lines | hook + git floor |
| State | HANDOFF.md | overwrite-only, ≤ 40 lines, required sections | hook + git floor |
| State | TASKS.md | stable T-NNNN ids; mutable checkbox/detail/order | hook + git floor + doctor |
| Log | DECISIONS.md | append-only, insertions only, supersede-never-edit | hook + git floor |
| Plan | ROADMAP.md, plans/ → plans/archive/ (frozen) | archive immutable | hook + git floor |

Plus a **bash guard** on every harness: shell writes to governed files
(`>>`, `sed -i`, `tee`, ...) are denied — the editor tools are the audited
path. Automatic adapters stay silent outside a repository explicitly marked
by `.statutor.yaml`. A complete quoted heredoc used as `git commit -F -`
message data is not scanned as shell code; its opener and all actual command
lines remain guarded. No hand-maintained CHANGELOG.md: git log + conventional
commits.

State task identities are durable: an existing ID cannot disappear or be
renamed, while its checkbox, detail, and position may change. New IDs advance
beyond the committed maximum. v0.4 intentionally has no pruning operation;
completed entries remain until a separately specified identity-preserving
archive exists (D-0016).

## Kernel / adapter architecture

    core/statutor_core.py     single-file kernel: validate() + embedded templates
                          modes: hook | check | staged | init | trust approve
                          (fail-open hooks; staged floor fails closed)
    core/statutor_doctor.py   drift linter (stale stamps, budgets, unarchived plans)
    core/statutor_global.py   global-layer roots, schemas, hashes, CAS, backups
    core/statutor_global_cli.py  opt-in global instruction lifecycle and CLI
    core/statutor_skills.py   portable Agent Skill validation and projections
    hooks/stop_doctor.py  Claude Code Stop hook: runs statutor-doctor after each
                          turn and surfaces its WARN/ERROR lines as
                          additionalContext — non-blocking, silent when the
                          ledger is clean or the cwd isn't a statutor ledger at all
    pyproject.toml        pipx install → `statutor`, `statutor-doctor` on PATH

| Adapter | Mechanism | Coverage |
|---|---|---|
| Claude Code (repo root is the plugin) | PreToolUse `Write\|Edit\|Bash\|apply_patch` → `statutor hook`; Stop → `hooks/stop_doctor.py` | full in-loop + drift surfacing |
| OpenCode (`adapters/opencode/statutor.ts`) | `tool.execute.before` → `statutor check --if-ledger` | in-loop (write/edit/bash)¹ |
| Codex CLI (`adapters/codex/`) | PreToolUse (Claude-compatible protocol) → `statutor hook` | bash guard + apply_patch² |
| git (`adapters/git/`, `.pre-commit-hooks.yaml`) | `statutor staged` in local pre-commit and CI | staged-index backstop |
| native (`crates/statutor/`) | `statutor-staged`, conformance-gated ≡ Python | local staged floor without Python |
| Custom harnesses (`statutor check`, or import `validate`) | embed in your own tool dispatch | full in-loop |

¹ in-loop for write/edit/bash/apply_patch; the kernel parses apply_patch
envelopes (T-0011), with two partial-diff blind spots: required sections
on an Update File and server-namespaced MCP tool ids — the git floor
covers both. Subagent tool calls
DO fire plugin hooks (verified opencode v1.18.21, 2026-08-21); the
opposite claim (sst/opencode#5894) was a misdiagnosis, stale-closed
2026-04-15.
² Codex hooks are on by default since rust-v0.124.0 (2026-04-23) — the old
`[features].codex_hooks` flag is a deprecated legacy alias, and hooks need
a one-time trust approval (`/hooks`). Codex sends edits as tool_name
`apply_patch` + `{"command":
"<envelope>"}`, which `guard_apply_patch()` parses (frozen/delete/
append-only/cap checks; see adapters/codex/). Residual gaps: MCP tools
and Update-File section checks — so the git floor remains
mandatory there.

## Install

    pipx install statutor                # or: pip install -e .
    statutor init .                      # scaffold any repo, any harness

    # Claude Code (this repo doubles as the plugin):
    /plugin marketplace add https://github.com/hoohugokim/statutor
    /plugin install statutor@hoo-plugins --scope project
    # then: /statutor-init  /handoff  /decide  /statutor-doctor

    # .pre-commit-config.yaml
    repos:
      - repo: https://github.com/hoohugokim/statutor
        rev: v0.4.0
        hooks: [{id: statutor}]

Per-repo policy lives in `.statutor.yaml`. In-loop checks use the committed
HEAD snapshot; the git floor judges the transaction under both HEAD and the
candidate index snapshot, so an unstaged or co-staged weakening cannot disable
existing rules. The format is a strict, zero-dependency YAML subset shared by
Python and Rust; malformed or unsupported committed/candidate policy denies.
Before the marker's first commit, automatic hooks use embedded defaults. An
edited worktree policy does not change hook behavior until it passes trust
approval and becomes HEAD in a separate commit.

After bootstrap, changing `.statutor.yaml` or Statutor's exact
`CLAUDE.md` → `@AGENTS.md` bridge requires an exact-tree Git-local receipt:

    git add .statutor.yaml
    statutor trust approve . --decision D-0015 --reason "why this changes trust"
    statutor staged .

Approval displays the reserved diff and all staged paths, then requires the
complete candidate tree ID. The mode-0600 receipt expires on any HEAD or index
change and is never committed.

## Release gate

With Python `build`/`pytest`, Cargo, and npm available, stage the candidate and
run `python scripts/release_gate.py`. The gate tests the exact Git index, audits
all package payloads, builds the Python sdist and wheel in scratch space,
installs the wheel into an isolated target, and smoke-tests both console
scripts. A tagged release additionally passes `--tag vX.Y.Z --dist-dir dist`;
verified artifacts are copied only after every check succeeds.

The v0.4 global layer also has a separate, opt-in current-host probe:
`python scripts/global_e2e.py --json`. It pins the tested Claude, Codex, and
OpenCode versions, rehomes every host under a temporary profile, performs no
model or network request, and proves native discovery where an offline surface
exists, modified-target refusal, and exact uninstall recovery. It is not part
of the hermetic release gate and never mutates the caller's real home.

## Portable user layer (v0.4)

The global layer is opt-in and separate from project ledgers. `init` creates
only human-owned canonical sources and versioned state; it does not change any
host file. `plan`, `status`, and `--json` are read-only. `apply` owns only
whole generated files it created, while `adopt HOST` backs up an existing
regular file and imports its bytes verbatim into that host's canonical overlay.

    statutor global init
    statutor global plan --json
    statutor global apply --host codex
    statutor global status --json
    statutor global doctor --json
    statutor global adopt claude
    statutor global uninstall --host codex

    statutor global skill import ./my-skill
    statutor global skill plan --json
    statutor global skill apply
    statutor global skill status --json
    statutor global skill sync
    statutor global skill uninstall

Every mutation prints its resolved plan first. Existing unmanaged targets are
conflicts, managed hand edits are never overwritten or removed, and uninstall
restores the original backup. `--home`, `--config-root`, and `--state-root`
provide explicit isolated roots for tests and alternate profiles. Codex
overrides and OpenCode's Claude fallback are reported as precedence warnings;
Statutor never rewrites them.

Imported skills are copied to a new human-owned canonical source, then
projected as complete trees to `$HOME/.agents/skills` and Claude's personal
skills root. Core `SKILL.md` metadata and the complete tree are validated;
host-specific frontmatter is preserved. Identical unmanaged trees require
explicit `--adopt-identical`, differing or hand-edited trees are conflicts,
and names in a foreign `.agents/.skill-lock.json` remain entirely foreign.
OpenCode discovers the portable and Claude projections, so Statutor reports
whether those duplicates are identical instead of creating a third native
OpenCode copy.

Unified `global status` is a fast, read-only inventory of effective instruction
precedence, ownership, disabled/foreign skills, duplicate names, legacy/native/
admin/plugin roots, and catalog size. `global doctor` performs the deeper full-
tree audit: managed drift and receipt topology, generated headers, unsafe links,
active divergent duplicates, Codex's configured instruction cap, and Statutor's
32 KiB skill-description diagnostic budget (reported explicitly as a Statutor
budget, not a host limit). Status exits zero when inventory completes; doctor
exits one when the audit contains errors. Neither command invokes a host binary
or performs a network request.

## Provenance

Framework doctrine distilled from: the AGENTS.md open standard
<https://agents.md/>, Claude Code memory & hooks docs
<https://code.claude.com/docs/en/memory>, <https://code.claude.com/docs/en/hooks>,
Anthropic on long-running agent harnesses
<https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
and context engineering
<https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>,
MADR <https://adr.github.io/madr/>, Keep a Changelog
<https://keepachangelog.com/>, Conventional Commits
<https://www.conventionalcommits.org/>, pre-commit <https://pre-commit.com/>.
