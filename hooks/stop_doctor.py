#!/usr/bin/env python3
"""statutor Stop hook — run statutor-doctor and surface WARN/ERROR without blocking.

Reads the Stop event off stdin, resolves the project directory from the
event's `cwd` (not ${CLAUDE_PROJECT_DIR} — cwd tracks Claude's actual
working directory, e.g. inside a worktree), and shells out to
core/statutor_doctor.py located relative to this file (not via console script:
the plugin may be used without `pip install`).

Silent + exit 0 on a clean ledger, AND silent + exit 0 outside a statutor
ledger entirely (no AGENTS.md and no .statutor.yaml at the resolved project
dir) — this plugin can be installed at user scope, so every non-statutor repo,
and every session where Claude has cd'd into a subdirectory of one, must
not pay a spurious continuation on every turn.

Fails open on anything unexpected (bad stdin, missing doctor script,
doctor crash/timeout): a broken linter must never trap the user in the
session. Never re-fires once this turn has already been continued once
(stop_hook_active), bounding us to at most one continuation per turn.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

DOCTOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core", "statutor_doctor.py")

# The scaffolded HANDOFF.md template ships an unfilled `last_verified:
# 1970-01-01` sentinel (core/statutor_core.py TEMPLATES, not editable here).
# On a fresh `statutor init` that sentinel is ~20000 days stale, which would
# otherwise trip this hook on the very first Stop after scaffolding. A
# single WARN naming exactly that sentinel date is treated as init-state
# noise, not drift, and suppressed.
_SENTINEL_STALE_WARN_PREFIX = "WARN  HANDOFF.md last verified"
_SENTINEL_DATE = "1970-01-01"


def _looks_like_ledger(project_dir: str) -> bool:
    return os.path.isfile(os.path.join(project_dir, "AGENTS.md")) or \
        os.path.isfile(os.path.join(project_dir, ".statutor.yaml"))


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return 0  # not an object: fail open
    except Exception:
        return 0  # can't parse input: fail open

    if event.get("stop_hook_active"):
        return 0  # already continued once this turn: surface once, then get out of the way

    project_dir = event.get("cwd") or os.getcwd()

    if not _looks_like_ledger(project_dir):
        return 0  # not a statutor ledger: stay completely out of the way

    try:
        result = subprocess.run(
            ["python3", DOCTOR, project_dir],
            capture_output=True, text=True, timeout=20,
        )
    except Exception:
        return 0  # doctor itself broke or hung: fail open

    findings = [
        line for line in (result.stdout + result.stderr).splitlines()
        if line.startswith("WARN") or line.startswith("ERROR")
    ]

    handoff_stamp_present = os.path.isfile(os.path.join(project_dir, "HANDOFF.md"))
    if (handoff_stamp_present and len(findings) == 1
            and findings[0].startswith(_SENTINEL_STALE_WARN_PREFIX)):
        try:
            handoff_text = open(os.path.join(project_dir, "HANDOFF.md"), encoding="utf-8").read()
        except Exception:
            handoff_text = ""
        if f"last_verified: {_SENTINEL_DATE}" in handoff_text:
            findings = []  # untouched scaffold: init-state noise, not drift

    if not findings:
        return 0  # clean ledger (or only-sentinel scaffold): completely silent

    report = "\n".join(findings)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": f"statutor-doctor found drift in the ledger:\n{report}",
        },
        "systemMessage": f"statutor-doctor: {len(findings)} issue(s) found — see transcript.",
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
