#!/usr/bin/env python3
"""statutor — typed project-ledger kernel (harness-agnostic).

Four planes (constitution / state / log / plan), one writer per file,
mutation policies enforced here rather than in prose.

Entry modes (all share the same validate() core):

  statutor hook           Claude Code / Codex CLI hook protocol:
                          stdin JSON in, permissionDecision JSON out.
                          (Codex's PreToolUse mirrors Claude's schema and
                          also fires for apply_patch, but sends edits as
                          tool_input {"command": "<patch text>"} — this
                          validate() only understands bash/write/edit, so
                          apply_patch falls through unhandled; the git
                          floor is mandatory there. See adapters/codex/.)
  statutor check TOOL JSON [CWD]
                          Generic shim mode for OpenCode / Hermes / tests.
                          exit 0 = allow, exit 2 = deny (reason on stderr).
  statutor staged [CWD]   Git floor: validate staged changes (pre-commit).
                          exit 1 on violations.
  statutor init [DIR]     Scaffold governed files from embedded templates.

No third-party dependencies. PyYAML optional (.statutor.yaml overrides).
Hook mode fails open: a kernel bug must never break a session.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys

# --------------------------------------------------------------------------
# policy
# --------------------------------------------------------------------------

DEFAULT_POLICY: dict = {
    "bash_guard": True,
    "governed": [
        {"pattern": "AGENTS.md", "policy": "constitution", "hard_max_lines": 200},
        {
            "pattern": "HANDOFF.md",
            "policy": "overwrite_bounded",
            "max_lines": 40,
            "required_sections": [
                "## Goal",
                "## Last verified state",
                "## Next action",
                "## Gotchas",
                "## Do not touch",
            ],
        },
        {"pattern": "DECISIONS.md", "policy": "append_only"},
        {"pattern": "TASKS.md", "policy": "state"},
        {"pattern": "plans/archive/*", "policy": "frozen"},
    ],
}

WRITEISH = ("(?<![0-9<>])>", ">>", "\\btee\\b", "\\bsed\\s+-i", "\\brm\\b",
            "\\bmv\\b", "\\btruncate\\b", "\\bdd\\b", "\\bcp\\b")


def load_policy(cwd: str) -> dict:
    path = os.path.join(cwd, ".statutor.yaml")
    if os.path.isfile(path):
        try:
            import yaml  # optional

            data = yaml.safe_load(open(path, encoding="utf-8"))
            if isinstance(data, dict) and "governed" in data:
                data.setdefault("bash_guard", True)
                return data
        except Exception:
            pass  # fall through to defaults; `statutor doctor` reports parse issues
    return DEFAULT_POLICY


def _match_rule(rel_path: str, policy: dict) -> dict | None:
    rel_path = rel_path.replace(os.sep, "/")
    base = os.path.basename(rel_path)
    for rule in policy.get("governed", []):
        pat = rule.get("pattern", "")
        if fnmatch.fnmatch(rel_path, pat) or fnmatch.fnmatch(base, pat):
            return rule
    return None


def _norm(payload: dict) -> dict:
    """Normalize harness arg names (Claude snake_case, OpenCode camelCase)."""
    out = dict(payload or {})
    for a, b in (("filePath", "file_path"), ("oldString", "old_string"),
                 ("newString", "new_string")):
        if a in out and b not in out:
            out[b] = out[a]
    return out


# --------------------------------------------------------------------------
# core validation (pure): returns denial reason or None
# --------------------------------------------------------------------------

def validate(tool: str, payload: dict, cwd: str, policy: dict | None = None) -> str | None:
    policy = policy or load_policy(cwd)
    tool = tool.lower()
    payload = _norm(payload)

    if tool == "bash":
        return guard_bash(payload.get("command", ""), policy)
    if tool not in ("write", "edit"):
        return None

    file_path = payload.get("file_path", "")
    if not file_path:
        return None
    rel = os.path.relpath(os.path.abspath(file_path), os.path.abspath(cwd))
    rule = _match_rule(rel, policy)
    if rule is None:
        return None
    kind = rule.get("policy", "")

    if kind == "frozen":
        return f"{rel} is frozen (archived plan). Archived records are immutable."

    if kind == "constitution" and tool == "write":
        content = payload.get("content", "")
        hard = int(rule.get("hard_max_lines", 200))
        n = content.count("\n") + 1
        if n > hard:
            return (f"AGENTS.md would be {n} lines (hard cap {hard}). The constitution "
                    "carries only what the repo cannot say itself — move procedures "
                    "to skills/commands, delete derivable facts.")

    if kind == "overwrite_bounded" and tool == "write":
        content = payload.get("content", "")
        cap = int(rule.get("max_lines", 40))
        n = content.count("\n") + 1
        if n > cap:
            return (f"{rel} would be {n} lines (cap {cap}). HANDOFF is a shift-change "
                    "note, not a log: overwrite, compress, drop history.")
        missing = [s for s in rule.get("required_sections", []) if s not in content]
        if missing:
            return (f"{rel} is missing required sections: {', '.join(missing)}. "
                    "A handoff without these fields strands the next session.")

    if kind == "append_only":
        if tool == "edit":
            old = payload.get("old_string", "")
            new = payload.get("new_string", "")
            if old and old not in new:
                return (f"{rel} is append-only. Edits must be pure insertions "
                        "(new_string must contain old_string verbatim). To change a "
                        "decision, append a superseding record — never edit the old one.")
        elif tool == "write":
            try:
                existing = open(file_path, encoding="utf-8").read()
            except FileNotFoundError:
                existing = ""
            if existing.strip() and existing.strip() not in payload.get("content", ""):
                return (f"{rel} is append-only. A full rewrite must contain the "
                        "existing content verbatim; records are never modified or deleted.")
    return None


def guard_bash(command: str, policy: dict) -> str | None:
    """Deny shell commands that look like writes to governed files.

    Closes the bypass where an agent avoids Write/Edit hooks via
    `echo x >> DECISIONS.md` or `sed -i` — on every harness, and it is the
    only PreToolUse coverage Codex currently offers. Strict by design
    (a redirect on the same line as a governed name is denied even if the
    target differs); disable per-repo with `bash_guard: false` in .statutor.yaml.
    """
    if not policy.get("bash_guard", True) or not command:
        return None
    names = [os.path.basename(r.get("pattern", "")) for r in policy.get("governed", [])
             if r.get("policy") in ("append_only", "overwrite_bounded", "constitution")
             and "*" not in r.get("pattern", "")]
    hit = [n for n in names if n and n in command]
    if hit and any(re.search(p, command) for p in WRITEISH):
        return (f"shell write touching governed file(s) {hit} denied: direct shell "
                "mutations bypass policy validation. Use the editor tool, or set "
                "bash_guard: false in .statutor.yaml if this was a false positive.")
    return None


# --------------------------------------------------------------------------
# entry: hook (Claude Code / Codex protocol) — must fail open
# --------------------------------------------------------------------------

def run_hook() -> int:
    try:
        event = json.load(sys.stdin)
        tool = event.get("tool_name", "")
        payload = event.get("tool_input", {}) or {}
        cwd = event.get("cwd", os.getcwd())
        reason = validate(tool, payload, cwd)
        if reason:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"[statutor] {reason}",
            }}))
    except Exception:
        pass  # fail open
    return 0


# --------------------------------------------------------------------------
# entry: check (generic shim for OpenCode / Hermes / tests)
# --------------------------------------------------------------------------

def run_check(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: statutor check TOOL JSON [CWD]", file=sys.stderr)
        return 64
    tool, payload = argv[0], json.loads(argv[1])
    cwd = argv[2] if len(argv) > 2 else os.getcwd()
    reason = validate(tool, payload, cwd)
    if reason:
        print(f"[statutor] {reason}", file=sys.stderr)
        return 2
    return 0


# --------------------------------------------------------------------------
# entry: staged (git floor — harness-independent backstop)
# --------------------------------------------------------------------------

def _git(cwd: str, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, check=False).stdout


def run_staged(cwd: str) -> int:
    policy = load_policy(cwd)
    violations: list[str] = []

    for line in _git(cwd, "diff", "--cached", "--name-status", "-M").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, paths = parts[0], parts[1:]
        old, new = (paths[0], paths[-1])
        for p, arriving in ((old, False), (new, True)) if status.startswith("R") \
                else ((new, status.startswith("A")),):
            rule = _match_rule(p, policy)
            if rule and rule.get("policy") == "frozen" and not arriving:
                violations.append(f"{p}: frozen — archived records are immutable "
                                  "(moving a plan INTO the archive is allowed).")

    for path in _git(cwd, "diff", "--cached", "--name-only").splitlines():
        rule = _match_rule(path, policy)
        if not rule:
            continue
        kind = rule.get("policy", "")
        if kind == "append_only":
            diff = _git(cwd, "diff", "--cached", "-U0", "--", path)
            dels = [l for l in diff.splitlines()
                    if l.startswith("-") and not l.startswith("---")]
            if dels:
                violations.append(
                    f"{path}: append-only, but staged diff deletes/modifies "
                    f"{len(dels)} line(s). Append superseding records instead.")
        elif kind in ("overwrite_bounded", "constitution"):
            blob = _git(cwd, "show", f":{path}")
            n = blob.count("\n") + 1
            cap = int(rule.get("max_lines", rule.get("hard_max_lines", 200)))
            if n > cap:
                violations.append(f"{path}: staged version is {n} lines (cap {cap}).")
            missing = [s for s in rule.get("required_sections", []) if s not in blob]
            if missing:
                violations.append(f"{path}: missing sections {missing}.")

    for v in violations:
        print(f"STATUTOR  {v}")
    return 1 if violations else 0


# --------------------------------------------------------------------------
# entry: init (embedded templates — single source of truth)
# --------------------------------------------------------------------------

TEMPLATES: dict[str, str] = {
    "AGENTS.md": """\
<!-- statutor: plane=constitution | policy=constitution | writer=human | budget: soft 120 / hard 200 lines -->
# AGENTS.md

> One-paragraph project statement and core constraints. Nothing derivable
> from the codebase belongs here — only pitfalls, rationale, and conventions
> that differ from tool defaults.

## Commands
- Build: `<cmd>`
- Test: `<cmd>`
- Lint: `<cmd>`

## Conventions that differ from defaults
- <...>

## Pitfalls (hard-won, one line each)
- <add only after an agent actually made the mistake>

## Boundaries
- Do not edit: `plans/archive/`, generated files
- Ledger discipline: HANDOFF.md (state), TASKS.md (queue), DECISIONS.md
  (settled questions — read before re-opening any choice)
""",
    "HANDOFF.md": """\
<!-- statutor: plane=state | policy=overwrite_bounded (max 40 lines) | writer=executor | OVERWRITE, NEVER APPEND -->
# HANDOFF

last_verified: 1970-01-01 by `<command that proved the state below>`

## Goal
<the single objective of the current work stream>

## Last verified state
<what is known-working right now, and how it was verified>

## Next action
<the exact next step, specific enough to start cold>

## Gotchas
<open traps discovered this session>

## Do not touch
<files/areas mid-flight or deliberately frozen>
""",
    "DECISIONS.md": """\
<!-- statutor: plane=log | policy=append_only (insertions only; supersede, never edit) | writer=orchestrator/human -->
# DECISIONS

## D-0001 — Adopt the statutor ledger framework
**Status:** accepted
**Context:** Multi-agent sessions re-litigate settled questions and lose state across context windows.
**Decision:** Four-plane typed ledger, single writer per file, hook-enforced mutation policies.
**Consequences:** HANDOFF.md is overwrite-only and bounded; this file is append-only; CHANGELOG.md is generated from conventional commits, never hand-maintained.
""",
    "TASKS.md": """\
<!-- statutor: plane=state | policy=state (doctor-checked) | writer=orchestrator | stable IDs, one line per task -->
# TASKS

- [ ] T-0001 <first task — imperative, verifiable>
""",
    "ROADMAP.md": """\
<!-- statutor: plane=plan | writer=human | agents read ONLY the section below the marker -->
# ROADMAP

## Current milestone <!-- agent-visible -->
<what "done" means for the active milestone>

## Later (human context, agents ignore)
- <...>
""",
    ".statutor.yaml": """\
# .statutor.yaml — statutor mutation policy. Embedded defaults apply if
# this file is absent or PyYAML is unavailable.
bash_guard: true
governed:
  - pattern: AGENTS.md
    policy: constitution
    hard_max_lines: 200
  - pattern: HANDOFF.md
    policy: overwrite_bounded
    max_lines: 40
    required_sections:
      - "## Goal"
      - "## Last verified state"
      - "## Next action"
      - "## Gotchas"
      - "## Do not touch"
  - pattern: DECISIONS.md
    policy: append_only
  - pattern: TASKS.md
    policy: state
  - pattern: plans/archive/*
    policy: frozen
""",
}


def run_init(target: str) -> int:
    os.makedirs(os.path.join(target, "plans", "archive"), exist_ok=True)
    os.makedirs(os.path.join(target, "notes"), exist_ok=True)
    for name, body in TEMPLATES.items():
        path = os.path.join(target, name)
        if os.path.exists(path):
            print(f"skip  {name} (exists)")
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        print(f"write {name}")
    claude_md = os.path.join(target, "CLAUDE.md")
    if not os.path.exists(claude_md):
        with open(claude_md, "w", encoding="utf-8") as fh:
            fh.write("@AGENTS.md\n")
        print("write CLAUDE.md (@AGENTS.md import)")
    return 0


# --------------------------------------------------------------------------

def main() -> None:
    argv = sys.argv[1:]
    mode = argv[0] if argv else "hook"
    if mode in ("hook", "--claude-hook"):
        sys.exit(run_hook())
    if mode == "check":
        sys.exit(run_check(argv[1:]))
    if mode in ("staged", "--staged"):
        sys.exit(run_staged(argv[1] if len(argv) > 1 else os.getcwd()))
    if mode == "init":
        sys.exit(run_init(argv[1] if len(argv) > 1 else os.getcwd()))
    print(__doc__)
    sys.exit(64)


if __name__ == "__main__":
    main()
