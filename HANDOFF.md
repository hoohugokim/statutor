<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 2026-09-20 by `/opt/homebrew/bin/python3.14 -m pytest -q` (564 passed/5 skipped) + `uv run --no-project --python /opt/homebrew/bin/python3.14 --with build --with pytest --with pip python scripts/release_gate.py` (OK) + doctor clean + staged floor clean
last_worker: unknown
last_machine: unknown
handoff_id: none
supersedes: none

## Goal
Ship v0.6.0 (T-0043 init profiles, D-0024). Agent side is complete on
`work/v0.6-init-profiles`; merge, tag, publish, and dogfood are human steps.

## Last verified state
Seven commits b6842a2..(this one) on `work/v0.6-init-profiles`, NOT pushed:
init profiles (`--type` > `STATUTOR_INIT_TYPE` > markers > `min`; `none`
opt-out; symlink-safe O_EXCL creates), D-0024, T-0043/T-0038 closed, v0.6
plan archived, Python/plugin 0.6.0 (npm/crate hold 0.1.1), Fowler doc items
in README/SKILL. Opus adversarial review: all D-0024 guarantees hold; its one
blocker (inherited symlink follow) fixed in 9375151. Floor/doctor/Rust
untouched (`git diff 2c2d0a3 HEAD --stat` on those paths is empty).

## Next action
1. Review `git log 2c2d0a3..HEAD -p`; fast-forward `main` to this branch.
2. `git tag v0.6.0 && git push origin main v0.6.0`: publish.yml reruns the
   gate and publishes to PyPI via trusted publishing; then `pipx upgrade statutor`.
3. Resume dogfood per `notes/v0.5-release-guide.md` §1/§4, one phase per
   approval; try `statutor init --type none` on a scratch repo first.

## Gotchas
System `python3` is 3.9 (< requires 3.10): use /opt/homebrew/bin/python3.14.
Plain `uv run` drops `.venv`/`uv.lock` into the repo; use the exact gate
command above. Host binaries drifted past pins (Claude 2.1.278, Codex 0.155.1,
OpenCode 1.18.30 vs 2.1.258/0.152.1/1.18.20): pins change only after §1
behavioral re-verification. AGENTS.md untouched (pitfalls need a real mistake).

## Do not touch
Embedded TEMPLATES and INIT_PROFILES (no templates/ or profiles/ dir); root
`.pre-commit-hooks.yaml`; plugin layout; plans/archive; real-home config and
capability pins except separately approved dogfood steps.
