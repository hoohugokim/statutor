# statutor × git — the staged-index floor

This local pre-commit/CI layer validates the current worktree index. It does
not inspect pushed ref ranges and is not a server-side pre-receive validator;
`--no-verify` remains an explicit unverified escape. Checks: governed record
files cannot disappear or leave their policy rule; append-only HEAD lines remain
byte-identical and ordered in the index; frozen paths deny direct arrival,
modification, and departure while allowing rename-in; HANDOFF/AGENTS staged
blobs are checked against physical-line caps and required sections. The
committed policy and candidate index policy both judge the transaction;
protected trust-root changes require an exact-tree local approval receipt.
Malformed policy and Git query failures deny.

`state` candidates must contain valid unique task IDs, retain every committed
ID, and allocate new IDs above the committed maximum. Checkbox, detail, and
ordering edits remain allowed.

`crates/statutor/` builds a native, conformance-gated twin binary
(`statutor-staged`) with byte-identical verdicts and no Python dependency.
It is a normal target-native Cargo build, not a promised static executable.

Preferred install via the pre-commit framework (uses .pre-commit-hooks.yaml
at the statutor repo root):

    # .pre-commit-config.yaml in your project
    repos:
      - repo: https://github.com/hoohugokim/statutor
        rev: v0.4.0
        hooks: [ { id: statutor } ]

Fallback: copy ./pre-commit into .git/hooks/. When the `statutor` CLI is
not on PATH, that script FAILS CLOSED (exit 1 with install instructions):
a floor that silently no-ops when its linter is missing isn't a floor, and
vendoring a second kernel copy under .statutor/ would fork the single
source of truth. `pipx install statutor` makes the branch unreachable;
`git commit --no-verify` remains the explicit human override.

For an intentional staged trust-root transition:

    statutor trust approve . --decision D-NNNN --reason "why"

The receipt is stored under Git's local state, mode 0600, and becomes stale if
either HEAD or any staged byte changes.
