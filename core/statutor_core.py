#!/usr/bin/env python3
"""statutor — typed project-ledger kernel (harness-agnostic).

Four planes (constitution / state / log / plan), one writer per file,
mutation policies enforced here rather than in prose.

Entry modes (all share the same validate() core):

  statutor hook           Claude Code / Codex CLI hook protocol:
                          stdin JSON in, permissionDecision JSON out.
                          (Codex's PreToolUse mirrors Claude's schema and
                          also fires for apply_patch, sending edits as
                          tool_input {"command": "<apply_patch envelope>"}.
                          validate() parses that envelope — see
                          guard_apply_patch(); unknown payload shapes fall
                          through unhandled, and the git floor stays
                          mandatory as the backstop. See adapters/codex/.)
  statutor check TOOL JSON [CWD]
                          Generic shim mode for OpenCode / custom harnesses / tests.
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
    if tool == "apply_patch":
        return guard_apply_patch(payload, cwd, policy)
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
# apply_patch envelope (Codex / opencode GPT-5-class edit path)
# --------------------------------------------------------------------------

_AP_HEADER_RE = re.compile(r"^\*\*\* (Update File|Add File|Delete File|Move to):\s*(.+?)\s*$")
_AP_OPS = {"update file": "update", "add file": "add", "delete file": "delete"}


def _patch_targets(text: str) -> list[dict]:
    """Split an apply_patch envelope into per-file ops, in document order.

    Each target: {op, path, move_to, plus, minus, content} where plus/minus
    are the raw hunk lines and content is an Add File's decoded body.
    Context (" "), hunk anchors (@@), and anything before *** Begin Patch
    are ignored — this is a policy scan, not a patch applier.
    """
    targets: list[dict] = []
    cur: dict | None = None
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "*** Begin Patch":
            inside = True
            continue
        if stripped == "*** End Patch":
            break
        if not inside:
            continue
        m = _AP_HEADER_RE.match(line)
        if m:
            kind, path = m.group(1).lower(), m.group(2)
            if kind == "move to":
                if cur is not None:
                    cur["move_to"] = path
                continue
            cur = {"op": _AP_OPS[kind], "path": path, "move_to": None,
                   "plus": [], "minus": [], "content": []}
            targets.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("+"):
            cur["plus"].append(line)
            cur["content"].append(line[1:])
        elif line.startswith("-"):
            cur["minus"].append(line)
    return targets


def _resolve_patch_path(path: str, cwd: str) -> str:
    """Policy-relative form of a patch path (same resolution write/edit get:
    absolute-ize against cwd, then relativize back)."""
    return os.path.relpath(os.path.abspath(os.path.join(cwd, path)), os.path.abspath(cwd))


def _size_reason(rel: str, kind: str, rule: dict, content: str) -> str | None:
    """Cap/sections denial for a fully-known body (write tool and Add File)."""
    n = content.count("\n") + 1
    if kind == "constitution":
        hard = int(rule.get("hard_max_lines", 200))
        if n > hard:
            return (f"{rel} would be {n} lines (hard cap {hard}). The constitution "
                    "carries only what the repo cannot say itself.")
    elif kind == "overwrite_bounded":
        cap = int(rule.get("max_lines", 40))
        if n > cap:
            return (f"{rel} would be {n} lines (cap {cap}). HANDOFF is a shift-change "
                    "note, not a log: overwrite, compress, drop history.")
        missing = [s for s in rule.get("required_sections", []) if s not in content]
        if missing:
            return (f"{rel} is missing required sections: {', '.join(missing)}. "
                    "A handoff without these fields strands the next session.")
    return None


def guard_apply_patch(payload: dict, cwd: str, policy: dict) -> str | None:
    """Policy-check an apply_patch envelope.

    Codex PreToolUse delivers edits as tool_name apply_patch with
    tool_input {"command": "<envelope>"}; opencode substitutes apply_patch
    for write/edit on GPT-5-class models. Semantics mirror the other layers:

      * any touch of a frozen path is denied (arrival INTO plans/archive/
        stays allowed, matching the staged rename rule);
      * Delete File on a governed constitution/overwrite_bounded/append_only
        path is denied wholesale — records are superseded, never removed
        (state-policy files stay deletable, matching the bash guard's gap);
      * Move to on those same record policies must remain under the identical
        rule; state lifecycle in-loop remains part of T-0027;
      * Add File on a sized policy runs the full cap + required-sections
        check (the body is fully known);
      * Update File on append_only denies any deleting/modifying hunk line;
        on sized policies it estimates the resulting line count from the
        on-disk file plus adds-minus-dels (required sections cannot be
        verified from a partial diff — the git floor covers that).

    Unknown payload shapes fall through silently (None): parsing here must
    never be load-bearing for enforcement the git floor also provides.
    """
    text = payload.get("command", payload.get("patch", ""))
    if not isinstance(text, str) or "*** Begin Patch" not in text:
        return None

    for t in _patch_targets(text):
        rel = _resolve_patch_path(t["path"], cwd)
        rule = _match_rule(rel, policy)
        kind = rule.get("policy", "") if rule else ""

        if t["op"] == "delete":
            if kind == "frozen":
                return f"{rel} is frozen (archived plan). Archived records are immutable."
            if kind in ("constitution", "overwrite_bounded", "append_only"):
                return (f"{rel} is governed ({kind}): apply_patch cannot delete it. "
                        "Records are superseded, never removed.")
            continue

        move_rel = _resolve_patch_path(t["move_to"], cwd) if t["move_to"] else None
        if move_rel is not None and kind == "frozen":
            return (f"{rel} is frozen (archived plan). Moving a record OUT of "
                    "the archive is denied.")
        if (move_rel is not None
                and kind in ("constitution", "overwrite_bounded", "append_only")
                and _match_rule(move_rel, policy) is not rule):
            return (f"{rel} is governed ({kind}): moving it to ungoverned path "
                    f"{move_rel} is denied. Keep it under the same policy rule.")

        if t["op"] == "add":
            if kind == "frozen":
                return f"{rel} is frozen (archived plan). Archived records are immutable."
            if rule is None:
                continue
            reason = _size_reason(rel, kind, rule, "\n".join(t["content"]))
            if reason:
                return reason
            continue

        # update
        if kind == "frozen":
            return f"{rel} is frozen (archived plan). Archived records are immutable."
        if rule is None:
            continue
        dels, adds = len(t["minus"]), len(t["plus"])
        if kind == "append_only":
            if dels:
                return (f"{rel} is append-only, but the patch deletes/modifies "
                        f"{dels} line(s). Append superseding records instead.")
            continue
        if kind in ("constitution", "overwrite_bounded") and (adds or dels):
            cap_key = "hard_max_lines" if kind == "constitution" else "max_lines"
            cap = int(rule.get(cap_key, 200))
            try:
                cur_n = open(os.path.join(cwd, rel), encoding="utf-8").read().count("\n") + 1
            except OSError:
                cur_n = None  # unreadable/unmapped path: let the floor judge
            if cur_n is not None and cur_n + adds - dels > cap:
                est = cur_n + adds - dels
                return (f"{rel} would grow to ~{est} lines (cap {cap}).")
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
# entry: check (generic shim for OpenCode / custom harnesses / tests)
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

class _GitFailure(RuntimeError):
    """A floor-mode Git operation failed; never silently reinterpret it."""


def _git_bytes(cwd: str, *args: str) -> bytes:
    """Run one floor-mode Git query and return exact stdout bytes.

    Hook mode still fails open at its outer boundary. The staged floor does
    not: an absent repository, bare repository, unreadable index, or failed
    blob lookup means Statutor could not prove the transaction safe.
    """
    command = ["git", "-c", "color.ui=false", *args]
    display = "git " + " ".join(args)
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, check=False)
    except OSError as exc:
        raise _GitFailure(
            f"{display} could not start; staged validation requires a non-bare "
            "Git worktree with a readable index.") from exc
    if result.returncode != 0:
        raise _GitFailure(
            f"{display} failed (exit {result.returncode}); staged validation "
            "requires a non-bare Git worktree with a readable index.")
    return result.stdout


def _git(cwd: str, *args: str) -> str:
    return _git_bytes(cwd, *args).decode("utf-8", "replace")


def _staged_changes(cwd: str) -> list[tuple[str, str | None, str | None]]:
    """Return `(status, old_path, new_path)` from NUL-delimited Git output."""
    worktree = _git_bytes(cwd, "rev-parse", "--is-inside-work-tree").strip()
    if worktree != b"true":
        raise _GitFailure(
            "git rev-parse --is-inside-work-tree reported no worktree; staged "
            "validation requires a non-bare Git worktree with a readable index.")
    args = ("diff", "--cached", "--name-status", "-z", "-M")
    fields = _git_bytes(cwd, *args).split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    changes: list[tuple[str, str | None, str | None]] = []
    i = 0
    while i < len(fields):
        status = fields[i].decode("ascii", "replace")
        i += 1
        paths_needed = 2 if status.startswith(("R", "C")) else 1
        if not status or i + paths_needed > len(fields):
            raise _GitFailure(
                "git diff --cached --name-status -z -M returned malformed output; "
                "staged validation cannot safely identify changed paths.")
        paths = [p.decode("utf-8", "replace")
                 for p in fields[i:i + paths_needed]]
        i += paths_needed
        code = status[0]
        if code == "A":
            changes.append((status, None, paths[0]))
        elif code == "D":
            changes.append((status, paths[0], None))
        elif code in ("R", "C"):
            changes.append((status, paths[0], paths[1]))
        else:
            changes.append((status, paths[0], paths[0]))
    return changes


def _line_chunks(blob: bytes) -> list[bytes]:
    """Split on LF while retaining it, matching Git's line identity model."""
    if not blob:
        return []
    parts = blob.split(b"\n")
    lines = [part + b"\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _is_pure_line_insertion(before: bytes, after: bytes) -> bool:
    """True when every original line survives byte-for-byte and in order."""
    original = _line_chunks(before)
    if not original:
        return True
    matched = 0
    for candidate in _line_chunks(after):
        if candidate == original[matched]:
            matched += 1
            if matched == len(original):
                return True
    return False


_LIFECYCLE_POLICIES = {"constitution", "overwrite_bounded", "append_only", "state"}


def _frozen_reason(path: str) -> str:
    return (f"{path}: frozen — archived records are immutable "
            "(moving a plan INTO the archive is allowed).")


def _direct_frozen_add_reason(path: str) -> str:
    return (f"{path}: frozen — direct additions to the archive are denied "
            "(move an existing plan INTO the archive instead).")


def _lifecycle_reason(path: str, kind: str, destination: str | None) -> str:
    if destination is None:
        return (f"{path}: governed ({kind}) record cannot be deleted; "
                "supersede it without removing its governed path.")
    return (f"{path}: governed ({kind}) record cannot move to ungoverned path "
            f"{destination}; keep it under the same policy rule.")


def run_staged(cwd: str) -> int:
    policy = load_policy(cwd)
    violations: list[str] = []
    try:
        changes = _staged_changes(cwd)

        # Pass 1: record lifecycle and frozen-path transitions.
        for status, old, new in changes:
            code = status[0]
            old_rule = _match_rule(old, policy) if old is not None else None
            new_rule = _match_rule(new, policy) if new is not None else None
            old_kind = old_rule.get("policy", "") if old_rule else ""
            new_kind = new_rule.get("policy", "") if new_rule else ""

            if code == "D":
                if old_kind == "frozen":
                    violations.append(_frozen_reason(old))
                elif old_kind in _LIFECYCLE_POLICIES:
                    violations.append(_lifecycle_reason(old, old_kind, None))
                continue

            if code == "R":
                if old_kind == "frozen":
                    violations.append(_frozen_reason(old))
                elif (old_kind in _LIFECYCLE_POLICIES
                      and new_rule is not old_rule):
                    violations.append(_lifecycle_reason(old, old_kind, new))
                # A rename is the sole supported way to arrive in frozen.
                continue

            if new_kind == "frozen":
                if code in ("A", "C"):
                    violations.append(_direct_frozen_add_reason(new))
                else:
                    violations.append(_frozen_reason(new))

        # Pass 2: policies on candidate blobs. Deleted paths have no candidate.
        for status, old, path in changes:
            if path is None:
                continue
            rule = _match_rule(path, policy)
            if not rule:
                continue
            kind = rule.get("policy", "")
            code = status[0]
            if kind == "append_only":
                baseline = b""
                old_rule = _match_rule(old, policy) if old is not None else None
                if (code in ("M", "T") or
                        (code == "R" and old_rule is rule)):
                    baseline = _git_bytes(cwd, "show", f"HEAD:{old}")
                candidate = _git_bytes(cwd, "show", f":{path}")
                if not _is_pure_line_insertion(baseline, candidate):
                    violations.append(
                        f"{path}: append-only, but staged content deletes, rewrites, "
                        "or reorders existing lines. Append superseding records instead.")
            elif kind in ("overwrite_bounded", "constitution"):
                blob = _git_bytes(cwd, "show", f":{path}").decode("utf-8", "replace")
                n = blob.count("\n") + 1
                cap = int(rule.get("max_lines", rule.get("hard_max_lines", 200)))
                if n > cap:
                    violations.append(f"{path}: staged version is {n} lines (cap {cap}).")
                missing = [s for s in rule.get("required_sections", []) if s not in blob]
                if missing:
                    violations.append(f"{path}: missing sections {missing}.")
    except _GitFailure as exc:
        print(f"STATUTOR  {exc}")
        return 1

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
