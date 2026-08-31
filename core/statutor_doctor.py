#!/usr/bin/env python3
"""statutor doctor — drift linter for governed files.

Run from the repo root (or pass the root as argv[1]). Checks what the
PreToolUse hook cannot catch synchronously:

  * .statutor.yaml malformed or outside Statutor's deterministic YAML subset
  * governed files missing entirely
  * the constitution file over soft budget (hook only enforces the hard cap)
  * the overwrite_bounded file's stale `last_verified:` stamp (default:
    warn > 3 days)
  * the overwrite_bounded file missing required sections while it exists on
    disk (the hook/floor bounds writes; a file lacking sections means one
    was bypassed — that's drift)
  * consumed plans left in plans/ instead of plans/archive/
    (heuristic: plan references a TASKS.md id whose checkbox is [x])
  * DECISIONS.md records missing status fields

Budgets and filenames are read from the repo's policy (.statutor.yaml via
statutor_core.load_policy), falling back to the module constants below when a
key (or the whole rule) is absent:
  * the missing-file check list comes from governed patterns that are plain
    basenames (no "*", no "/")
  * the constitution filename comes from the constitution rule's pattern
    (same basename-only restriction); soft budget: optional `soft_max_lines`
  * the overwrite_bounded filename comes from that rule's pattern (same
    restriction); staleness threshold: optional `stale_after_days`;
    required sections: optional `required_sections`
  * the state-plane (TASKS) filename and the append-only (DECISIONS)
    filename come from their rules' patterns (same restriction); the plans/
    directory itself stays conventional — `statutor init` scaffolds it and
    no governed basename can express a directory

Exit code 1 on errors, 0 on clean/warnings-only.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime

import statutor_core

SOFT_AGENTS_LINES = 120
HANDOFF_STALE_DAYS = 3

errors: list[str] = []
warnings: list[str] = []


def _rule_filename(rule: dict | None, default: str) -> str:
    """Basename to check for `rule`, derived from its `pattern` when that
    pattern is a plain basename (no "*", no "/"); otherwise `default`.

    A glob or path pattern doesn't identify one single file to open for a
    line-count/staleness/sections check, so such rules fall back to the
    conventional name rather than guessing which match to inspect.
    """
    if rule:
        pat = rule.get("pattern", "")
        if pat and "*" not in pat and "/" not in pat:
            return pat
    return default


def check(root: str) -> None:
    errors.clear()
    warnings.clear()

    def p(name: str) -> str:
        return os.path.join(root, name)

    try:
        policy = statutor_core.load_worktree_policy(root)
    except statutor_core._PolicyFailure as exc:
        errors.append(f"invalid .statutor.yaml: {exc}")
        policy = statutor_core.DEFAULT_POLICY
    governed = policy.get("governed", [])

    check_names = [
        rule["pattern"] for rule in governed
        if rule.get("pattern") and "*" not in rule["pattern"] and "/" not in rule["pattern"]
    ]

    constitution_rule = next((r for r in governed if r.get("policy") == "constitution"), None)
    agents_filename = _rule_filename(constitution_rule, "AGENTS.md")
    soft_agents_lines = int(constitution_rule.get("soft_max_lines", SOFT_AGENTS_LINES)) \
        if constitution_rule else SOFT_AGENTS_LINES

    overwrite_rule = next((r for r in governed if r.get("policy") == "overwrite_bounded"), None)
    handoff_filename = _rule_filename(overwrite_rule, "HANDOFF.md")
    handoff_stale_days = int(overwrite_rule.get("stale_after_days", HANDOFF_STALE_DAYS)) \
        if overwrite_rule else HANDOFF_STALE_DAYS

    state_rule = next((r for r in governed if r.get("policy") == "state"), None)
    tasks_filename = _rule_filename(state_rule, "TASKS.md")

    append_only_rule = next((r for r in governed if r.get("policy") == "append_only"), None)
    decisions_filename = _rule_filename(append_only_rule, "DECISIONS.md")

    for name in check_names:
        if not os.path.isfile(p(name)):
            errors.append(f"missing governed file: {name} (run /ledger-init)")

    if os.path.isfile(p(agents_filename)):
        n = sum(1 for _ in open(p(agents_filename), encoding="utf-8"))
        if n > soft_agents_lines:
            warnings.append(
                f"{agents_filename} is {n} lines (soft budget {soft_agents_lines}): "
                "trim derivable content, move procedures to skills."
            )

    if os.path.isfile(p(handoff_filename)):
        text = open(p(handoff_filename), encoding="utf-8").read()
        m = re.search(r"last_verified:\s*(\d{4}-\d{2}-\d{2})", text)
        if not m:
            errors.append(f"{handoff_filename} has no `last_verified: YYYY-MM-DD` stamp.")
        else:
            age = (date.today() - datetime.strptime(m.group(1), "%Y-%m-%d").date()).days
            if age > handoff_stale_days:
                warnings.append(
                    f"{handoff_filename} last verified {age} days ago — re-verify or rewrite."
                )

        required_sections = overwrite_rule.get("required_sections", []) if overwrite_rule else []
        missing_sections = [s for s in required_sections if s not in text]
        if missing_sections:
            errors.append(
                f"{handoff_filename} is missing required sections: "
                f"{', '.join(missing_sections)} — a file on disk without these "
                "bypassed the hook/floor (that's drift)."
            )

    done_ids: set[str] = set()
    if os.path.isfile(p(tasks_filename)):
        for line in open(p(tasks_filename), encoding="utf-8"):
            m = re.match(r"- \[x\]\s+(\S+)", line, re.IGNORECASE)
            if m:
                done_ids.add(m.group(1))

    plans_dir = p("plans")
    if os.path.isdir(plans_dir):
        for fname in os.listdir(plans_dir):
            fpath = os.path.join(plans_dir, fname)
            if not fname.endswith(".md") or not os.path.isfile(fpath):
                continue
            body = open(fpath, encoding="utf-8").read()
            hit = [t for t in done_ids if t in body]
            if hit:
                warnings.append(
                    f"plans/{fname} references completed task(s) {hit} — "
                    "move to plans/archive/ (consumed plans are stale intent)."
                )

    if os.path.isfile(p(decisions_filename)):
        body = open(p(decisions_filename), encoding="utf-8").read()
        records = re.findall(r"^## D-\d+", body, re.MULTILINE)
        statuses = re.findall(r"^\*\*Status:\*\*", body, re.MULTILINE)
        if len(statuses) < len(records):
            warnings.append(
                f"{decisions_filename}: {len(records)} records but only {len(statuses)} "
                "Status fields — every record needs one."
            )


def main() -> None:
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    check(root)
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    if not warnings and not errors:
        print("OK    ledger clean.")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
