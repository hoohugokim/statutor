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

Fallback: copy ./pre-commit into .git/hooks/. That script's own fallback
branch (used when `statutor` isn't on PATH) shells out to
`$(git rev-parse --show-toplevel)/.statutor/statutor_core.py` — `statutor init` never
creates a `.statutor/` directory, so that branch only works if you vendor the
kernel there yourself: `mkdir -p .statutor && cp <statutor checkout>/core/statutor_core.py .statutor/`.
Prefer having `statutor` on PATH (`pipx install statutor`) so the fallback
is never needed.
