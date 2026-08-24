# statutor-staged — the static git floor

A single static binary implementing **`staged` mode only**: byte-compatible
with `python3 core/statutor_core.py staged <dir>` (same exit codes, same
`STATUTOR  <violation>` lines), built for **server-side `pre-receive`
hooks** where no Python runtime exists.

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

* `frozen` paths (`plans/archive/*`): tamper/deletion denied; renames INTO
  the archive allowed, departures denied (both rename sides checked under `-M`)
* `append_only` files: any deleting/modifying line in the `-U0` staged diff
  denied
* `overwrite_bounded` / `constitution` files: staged blob judged against
  `max_lines` / `hard_max_lines` (fallback chain ends at 200) and
  `required_sections`

Policy: `<repo>/.statutor.yaml` parsed via yaml-rust2; absence, parse
failure, or a missing `governed` key falls back to embedded defaults,
identically to the Python kernel.

## Install

    cargo install --path crates/statutor        # from a checkout

The binary is `statutor-staged`, deliberately NOT named `statutor` — the
Python CLI owns that PATH name and they must coexist (D-0009's lesson).

## Server wiring

```git # pre-receive in the bare repo's hooks dir
#!/bin/sh
exec /usr/local/bin/statutor-staged "$(git rev-parse --show-toplevel)"
```

Fail-open character matches the Python floor: an absent repo/empty diff
exits 0.
