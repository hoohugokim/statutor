<!-- statutor: plane=plan | writer=human | runbook for T-0015..T-0018; archive when all four close -->
# Registry claims — statutor on PyPI, npm, crates.io

D-0010 mandates claiming the name the same day it is announced anywhere.
The repo stays PRIVATE until T-0015 lands. Executor: human (accounts and
tokens are yours). Placeholders live OUTSIDE this repo — suggested:
`~/workbench/statutor-placeholders/{npm,crate}/`.

## T-0015 — PyPI `statutor` (the real claim: upload the actual package)
PyPI refuses empty reservations (PEP 541), but statutor is a real, working
package — uploading v0.2.0 as-is IS the claim.
1. Account: <https://pypi.org/account/register/> → enable 2FA (mandatory).
2. Token: Account settings → API tokens → "Add API token", scope *entire
   account* (only option before the project exists). Copy the `pypi-...` string.
3. Build and upload from the repo root:
       cd ~/workbench/statutor
       pixi exec -s python=3.12 -s python-build python -m build
       pixi exec -s twine twine upload dist/*
   twine prompts for the API token. Username, if asked, is `__token__`.
4. Immediately after: delete the account-wide token, mint a new one scoped
   to project `statutor`.
5. v0.3 polish (NOT now): readme/license/urls metadata in pyproject, and a
   tagged-release publish workflow via PyPI "trusted publisher" so tokens
   disappear entirely. Versions are immutable — 0.2.0 is burned once up.

## T-0016 — npm placeholder `statutor` (REAL artifact — D-0014, built by T-0019)
Package source: `adapters/opencode/` in-repo (OpenCode adapter + docs).
    cd ~/workbench/statutor/adapters/opencode && npm login && npm publish --access public

## T-0017 — crates.io `statutor` (REAL artifact — D-0014, built by T-0020..T-0022)
Crate source: `crates/statutor/` (binary `statutor-staged`, conformance-gated
against the Python kernel). Publish only after the CI rust leg is green:
    cd ~/workbench/statutor/crates/statutor && cargo login <token> && cargo publish

## T-0018 — after T-0015: go public
    gh repo edit hoohugokim/statutor --visibility public
Optional, same logic, still unclaimed as of 2026-08-23: GitHub org
`statutor`; domains statutor.dev / .io / .com (none has even an A record).

## Done means
`pip install statutor` works; npm/crates pages point here; repo public.
Then archive this file (git mv into plans/archive/).
