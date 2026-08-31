# statutor-staged — the native local git floor

A native binary implementing **`staged` mode only**: byte-compatible
with `python3 core/statutor_core.py staged <dir>` (same exit codes, same
`STATUTOR  <violation>` lines). It validates the current staged index in a
non-bare working tree for local pre-commit hooks and CI. It does not consume
the ref-update stream required for a server-side pre-receive hook.

This is not a port of Statutor. The policy kernel stays canonical in
Python (`core/statutor_core.py`); this crate is a narrow, deliberately
dumb twin whose *existence license* is continuous behavioral equivalence:
[`tests/test_conformance_rust.py`](../../tests/test_conformance_rust.py)
runs ~30 scenario repos through both implementations and fails CI on any
divergence in exit code or output bytes (DECISIONS.md, D-0014). Interactive
surfaces — hook mode, `check`, bash guard, apply_patch parsing, init — do
not exist here and must never: they belong to the harnesses that have them.

## Scope

Enforced on staged changes only:

* governed constitution/state/log records: deletion and rename outside their
  matching policy rule denied
* `frozen` paths (`plans/archive/*`): tamper, deletion, and direct addition
  denied; renames INTO the archive allowed, departures denied
* `append_only` files: every HEAD line must survive byte-for-byte and in order
  in the index, independent of binary-diff and `.gitattributes` rendering
* `overwrite_bounded` / `constitution` files: staged blob judged against
  `max_lines` / `hard_max_lines` (fallback chain ends at 200) and
  `required_sections`
* any failed Git query or non-worktree invocation denies with an actionable
  floor error; only interactive hook mode retains its fail-open boundary

Policy: `<repo>/.statutor.yaml` parsed via yaml-rust2; absence, parse
failure, or a missing `governed` key falls back to embedded defaults,
identically to the Python kernel.

## Install

    cargo install --path crates/statutor        # from a checkout

The binary is `statutor-staged`, deliberately NOT named `statutor` — the
Python CLI owns that PATH name and they must coexist (D-0009's lesson).

## Local hook wiring

```sh
#!/bin/sh
# .git/hooks/pre-commit
repo_root="$(git rev-parse --show-toplevel)" || exit 1
exec statutor-staged "$repo_root"
```

The binary intentionally has no ref-range mode. A bare-repository hook needs
separate semantics that validate every pushed old/new object range.
