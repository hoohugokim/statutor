# statutor × git — the universal floor

Every harness and every human converges at `git commit`, so this layer is
enforcement nothing can route around (add a server-side pre-receive running
`statutor staged` for absolute enforcement). Checks: append-only = zero deleted
lines in DECISIONS.md's staged diff; frozen = no modification/deletion under
plans/archive/ (moving a plan INTO the archive is allowed); HANDOFF/AGENTS
staged blobs against caps and required sections.

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
