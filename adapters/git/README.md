# statutor × git — the universal floor

Every harness and every human converges at `git commit`, so this layer is
enforcement nothing can route around (add a server-side pre-receive running
`statutor staged` for absolute enforcement). Checks: governed record files
cannot disappear or leave their policy rule; append-only HEAD lines must remain
byte-identical and ordered in the index; frozen paths deny direct arrival,
modification, and departure while allowing rename-in; HANDOFF/AGENTS staged
blobs are checked against physical-line caps and required sections. The
committed policy and candidate index policy both judge the transaction;
protected trust-root changes require an exact-tree local approval receipt.
Malformed policy and Git query failures deny.

`state` candidates must contain valid unique task IDs, retain every committed
ID, and allocate new IDs above the committed maximum. Checkbox, detail, and
ordering edits remain allowed.

For servers without a Python runtime, `crates/statutor/` builds a static,
conformance-gated twin binary (`statutor-staged`) with byte-identical
verdicts — see its README and DECISIONS.md D-0014.

Preferred install via the pre-commit framework (uses .pre-commit-hooks.yaml
at the statutor repo root):

    # .pre-commit-config.yaml in your project
    repos:
      - repo: <your statutor repo url>
        rev: v0.2.0
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
