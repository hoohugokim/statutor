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

No third-party dependencies. The policy format is a deterministic YAML subset;
PyYAML is optional for ancillary tooling, never required by the trust floor.
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


class _PolicyFailure(RuntimeError):
    """A policy snapshot is present but cannot be interpreted safely."""


_POLICY_KINDS = {
    "constitution", "overwrite_bounded", "append_only", "state", "frozen",
}
_RULE_KEYS = {
    "pattern", "policy", "max_lines", "hard_max_lines", "soft_max_lines",
    "stale_after_days", "required_sections",
}
_INTEGER_KEYS = {
    "max_lines", "hard_max_lines", "soft_max_lines", "stale_after_days",
}


def _strip_yaml_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for i, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if char in ("'", '"'):
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == "#" and quote is None and (i == 0 or line[i - 1].isspace()):
            return line[:i].rstrip()
    return line.rstrip()


def _yaml_scalar(token: str, source: str, lineno: int):
    token = token.strip()
    if not token:
        raise _PolicyFailure(f"{source}:{lineno}: missing YAML scalar")
    if token.startswith('"'):
        try:
            value = json.loads(token)
        except (json.JSONDecodeError, TypeError) as exc:
            raise _PolicyFailure(
                f"{source}:{lineno}: invalid double-quoted scalar") from exc
        if not isinstance(value, str):
            raise _PolicyFailure(f"{source}:{lineno}: scalar must be a string")
        return value
    if token.startswith("'"):
        if len(token) < 2 or not token.endswith("'"):
            raise _PolicyFailure(f"{source}:{lineno}: invalid single-quoted scalar")
        return token[1:-1].replace("''", "'")
    lowered = token.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if token == "[]":
        return []
    if re.fullmatch(r"[+-]?\d+", token):
        return int(token)
    if token[0] in "[{&*!|>@`" or token in ("null", "Null", "NULL", "~"):
        raise _PolicyFailure(f"{source}:{lineno}: unsupported YAML scalar {token!r}")
    return token


def _mapping_entry(text: str, source: str, lineno: int) -> tuple[str, str]:
    if ":" not in text:
        raise _PolicyFailure(f"{source}:{lineno}: expected key: value")
    key, value = text.split(":", 1)
    key = key.strip()
    if not re.fullmatch(r"[a-z_]+", key):
        raise _PolicyFailure(f"{source}:{lineno}: invalid key {key!r}")
    return key, value.strip()


def parse_policy(blob: bytes | str, source: str = ".statutor.yaml") -> dict:
    """Parse Statutor's deliberately small, deterministic YAML subset.

    The policy floor cannot depend on PyYAML and cannot let Python and Rust
    disagree about YAML features.  Complex YAML (anchors, tags, flow maps,
    block scalars, implicit nulls) is rejected instead of guessed.
    """
    if isinstance(blob, bytes):
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _PolicyFailure(f"{source}: policy is not valid UTF-8") from exc
    else:
        text = blob
    top: dict = {}
    rules: list[dict] | None = None
    current: dict | None = None
    section_list: list[str] | None = None

    for lineno, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[:len(raw) - len(raw.lstrip())]:
            raise _PolicyFailure(f"{source}:{lineno}: tabs are not valid indentation")
        line = _strip_yaml_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line[indent:]

        if indent == 0:
            current = None
            section_list = None
            key, token = _mapping_entry(body, source, lineno)
            if key not in {"bash_guard", "governed"}:
                raise _PolicyFailure(f"{source}:{lineno}: unknown top-level key {key!r}")
            if key in top:
                raise _PolicyFailure(f"{source}:{lineno}: duplicate key {key!r}")
            if key == "bash_guard":
                value = _yaml_scalar(token, source, lineno)
                if not isinstance(value, bool):
                    raise _PolicyFailure(f"{source}:{lineno}: bash_guard must be boolean")
                top[key] = value
            else:
                if token:
                    value = _yaml_scalar(token, source, lineno)
                    if value != []:
                        raise _PolicyFailure(f"{source}:{lineno}: governed must be a list")
                    rules = []
                else:
                    rules = []
                top[key] = rules
            continue

        if rules is None or "governed" not in top:
            raise _PolicyFailure(f"{source}:{lineno}: content must belong to governed")
        if indent == 2 and body.startswith("- "):
            current = {}
            rules.append(current)
            section_list = None
            key, token = _mapping_entry(body[2:], source, lineno)
        elif indent == 4 and current is not None:
            section_list = None
            key, token = _mapping_entry(body, source, lineno)
        elif indent == 6 and body.startswith("- ") and section_list is not None:
            value = _yaml_scalar(body[2:].strip(), source, lineno)
            if not isinstance(value, str):
                raise _PolicyFailure(
                    f"{source}:{lineno}: required section must be a string")
            section_list.append(value)
            continue
        else:
            raise _PolicyFailure(f"{source}:{lineno}: unsupported policy indentation")

        if key not in _RULE_KEYS:
            raise _PolicyFailure(f"{source}:{lineno}: unknown rule key {key!r}")
        if key in current:
            raise _PolicyFailure(f"{source}:{lineno}: duplicate rule key {key!r}")
        if key == "required_sections":
            if token:
                value = _yaml_scalar(token, source, lineno)
                if value != []:
                    raise _PolicyFailure(
                        f"{source}:{lineno}: required_sections must be a list")
                current[key] = []
            else:
                current[key] = []
            section_list = current[key]
        else:
            current[key] = _yaml_scalar(token, source, lineno)

    if "governed" not in top or not isinstance(rules, list):
        raise _PolicyFailure(f"{source}: missing governed list")
    top.setdefault("bash_guard", True)
    for index, rule in enumerate(rules, 1):
        where = f"{source}: governed rule {index}"
        if not isinstance(rule.get("pattern"), str) or not rule["pattern"]:
            raise _PolicyFailure(f"{where} needs a non-empty string pattern")
        if rule.get("policy") not in _POLICY_KINDS:
            raise _PolicyFailure(f"{where} has unsupported policy {rule.get('policy')!r}")
        for key in _INTEGER_KEYS:
            if key not in rule:
                continue
            value = rule[key]
            if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value):
                value = int(value)
                rule[key] = value
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise _PolicyFailure(f"{where} {key} must be a non-negative integer")
        if "required_sections" in rule and not all(
                isinstance(item, str) and item for item in rule["required_sections"]):
            raise _PolicyFailure(f"{where} required_sections must contain strings")
    return top


def _run_git_optional(cwd: str, *args: str) -> tuple[int, bytes]:
    try:
        result = subprocess.run(
            ["git", "-c", "color.ui=false", *args], cwd=cwd,
            capture_output=True, check=False)
    except OSError:
        return 127, b""
    return result.returncode, result.stdout


def _head_policy_blob(cwd: str) -> bytes | None:
    code, _ = _run_git_optional(cwd, "rev-parse", "--verify", "--quiet", "HEAD")
    if code != 0:
        return None
    code, listing = _run_git_optional(cwd, "ls-tree", "-z", "HEAD", "--", ".statutor.yaml")
    if code != 0 or not listing:
        return None
    code, blob = _run_git_optional(cwd, "show", "HEAD:.statutor.yaml")
    if code != 0:
        raise _PolicyFailure("HEAD:.statutor.yaml could not be read")
    return blob


def load_policy(cwd: str) -> dict:
    """Load baseline B: committed policy, or defaults before the first one."""
    blob = _head_policy_blob(cwd)
    return DEFAULT_POLICY if blob is None else parse_policy(blob, "HEAD:.statutor.yaml")


def load_worktree_policy(cwd: str) -> dict:
    """Strictly parse the human-edited candidate for doctor/diagnostics."""
    path = os.path.join(cwd, ".statutor.yaml")
    if not os.path.isfile(path):
        return DEFAULT_POLICY
    with open(path, "rb") as stream:
        return parse_policy(stream.read(), ".statutor.yaml")


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


def _resolve_tool_path(file_path: str, cwd: str) -> tuple[str, str]:
    """Return `(absolute, policy-relative)` using the event/check CWD.

    Harnesses commonly send relative paths.  Resolving those against the
    kernel process CWD makes an explicit hook/check CWD ineffective and can
    select the wrong policy rule entirely.
    """
    absolute = file_path if os.path.isabs(file_path) else os.path.join(cwd, file_path)
    absolute = os.path.abspath(absolute)
    return absolute, os.path.relpath(absolute, os.path.abspath(cwd))


def _physical_line_count(content: str | bytes) -> int:
    """Count physical lines without inventing one after a trailing LF."""
    newline = b"\n" if isinstance(content, bytes) else "\n"
    if not content:
        return 0
    return content.count(newline) + (0 if content.endswith(newline) else 1)


_TASK_LINE_RE = re.compile(r"^- \[([ xX])\] (T-(\d{4,}))\s+(.+)$")


def _state_tasks(content: str, path: str) -> tuple[dict[str, tuple[int, str, str]], str | None]:
    """Parse one-line task entries; prose/headings remain unrestricted."""
    tasks: dict[str, tuple[int, str, str]] = {}
    for lineno, line in enumerate(content.splitlines(), 1):
        if not line.startswith("- ["):
            continue
        match = _TASK_LINE_RE.fullmatch(line)
        if not match:
            return {}, (f"{path}: state line {lineno} must be `- [ ] T-NNNN detail` "
                        "or `- [x] T-NNNN detail`.")
        checkbox, task_id, number, detail = match.groups()
        if task_id in tasks:
            return {}, f"{path}: duplicate state task ID {task_id}."
        tasks[task_id] = (int(number), checkbox.lower(), detail)
    return tasks, None


def _state_reason(path: str, candidate: str, baseline: str | None = None) -> str | None:
    candidate_tasks, error = _state_tasks(candidate, path)
    if error:
        return error
    if baseline is None:
        return None
    baseline_tasks, error = _state_tasks(baseline, f"HEAD:{path}")
    if error:
        return error
    missing = sorted(set(baseline_tasks) - set(candidate_tasks))
    if missing:
        return (f"{path}: state task IDs cannot disappear or change: {missing}. "
                "Keep completed tasks in place.")
    if baseline_tasks:
        maximum = max(value[0] for value in baseline_tasks.values())
        for task_id, (number, _, _) in candidate_tasks.items():
            if task_id not in baseline_tasks and number <= maximum:
                return (f"{path}: new task ID {task_id} must be greater than existing "
                        f"maximum T-{maximum:04d}.")
    return None


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
    absolute_path, rel = _resolve_tool_path(file_path, cwd)
    rule = _match_rule(rel, policy)
    if rule is None:
        return None
    kind = rule.get("policy", "")

    if kind == "frozen":
        return f"{rel} is frozen (archived plan). Archived records are immutable."

    if kind in ("constitution", "overwrite_bounded"):
        candidate: str | None = None
        if tool == "write":
            candidate = payload.get("content", "")
        else:
            old = payload.get("old_string", "")
            new = payload.get("new_string", "")
            if old:
                try:
                    existing = open(absolute_path, encoding="utf-8").read()
                except OSError:
                    existing = None
                if existing is not None and old in existing:
                    count = -1 if payload.get("replace_all", False) else 1
                    candidate = existing.replace(old, new, count)
        if candidate is not None:
            reason = _size_reason(rel, kind, rule, candidate)
            if reason:
                return reason

    if kind == "state":
        candidate: str | None = None
        try:
            existing = open(absolute_path, encoding="utf-8").read()
        except FileNotFoundError:
            existing = ""
        except OSError:
            existing = None
        if tool == "write":
            candidate = payload.get("content", "")
        elif existing is not None:
            old = payload.get("old_string", "")
            if old and old in existing:
                count = -1 if payload.get("replace_all", False) else 1
                candidate = existing.replace(old, payload.get("new_string", ""), count)
        if candidate is not None:
            reason = _state_reason(rel, candidate, existing)
            if reason:
                return reason

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
                existing = open(absolute_path, encoding="utf-8").read()
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
             if r.get("policy") in ("append_only", "overwrite_bounded", "constitution", "state")
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
    n = _physical_line_count(content)
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
      * Delete File on any governed record path is denied wholesale — records
        are superseded or completed, never removed;
      * Move to on any record policy must remain under the identical rule;
      * Add File on a sized policy runs the full cap + required-sections
        check (the body is fully known);
      * Update File on append_only denies any deleting/modifying hunk line;
        state updates must retain every removed task ID; sized policies
        estimate the resulting line count from the
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
            if kind in ("constitution", "overwrite_bounded", "append_only", "state"):
                return (f"{rel} is governed ({kind}): apply_patch cannot delete it. "
                        "Records are superseded, never removed.")
            continue

        move_rel = _resolve_patch_path(t["move_to"], cwd) if t["move_to"] else None
        if move_rel is not None and kind == "frozen":
            return (f"{rel} is frozen (archived plan). Moving a record OUT of "
                    "the archive is denied.")
        if (move_rel is not None
                and kind in ("constitution", "overwrite_bounded", "append_only", "state")
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
            if kind == "state":
                reason = _state_reason(rel, "\n".join(t["content"]))
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
        if kind == "state":
            removed_ids = {
                match.group(2) for line in t["minus"]
                if (match := _TASK_LINE_RE.fullmatch(line[1:]))
            }
            added_ids = {
                match.group(2) for line in t["plus"]
                if (match := _TASK_LINE_RE.fullmatch(line[1:]))
            }
            missing = sorted(removed_ids - added_ids)
            if missing:
                return (f"{rel}: patch removes or changes state task IDs {missing}. "
                        "Keep each ID and edit only its checkbox/detail.")
            for line in t["plus"]:
                if line[1:].startswith("- [") and not _TASK_LINE_RE.fullmatch(line[1:]):
                    return (f"{rel}: added state task line must use "
                            "`- [ ] T-NNNN detail` or `- [x] T-NNNN detail`.")
            continue
        if kind in ("constitution", "overwrite_bounded") and (adds or dels):
            cap_key = "hard_max_lines" if kind == "constitution" else "max_lines"
            cap = int(rule.get(cap_key, 200))
            try:
                cur_n = _physical_line_count(
                    open(os.path.join(cwd, rel), encoding="utf-8").read())
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
    try:
        reason = validate(tool, payload, cwd)
    except _PolicyFailure as exc:
        print(f"[statutor] committed policy invalid: {exc}", file=sys.stderr)
        return 2
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


_EXACT_CLAUDE_BRIDGES = {b"@AGENTS.md\n", b"@AGENTS.md"}
_TRUST_RECEIPT_VERSION = 1


def _head_oid(cwd: str) -> str | None:
    code, output = _run_git_optional(cwd, "rev-parse", "--verify", "--quiet", "HEAD")
    if code == 0:
        return output.decode("ascii").strip()
    if code in (1, 128):
        return None
    raise _GitFailure("git rev-parse --verify HEAD failed; trust state is unknown.")


def _head_entry(cwd: str, path: str) -> tuple[str, bytes] | None:
    if _head_oid(cwd) is None:
        return None
    listing = _git_bytes(cwd, "ls-tree", "-z", "HEAD", "--", path)
    if not listing:
        return None
    records = [record for record in listing.split(b"\0") if record]
    if len(records) != 1 or b"\t" not in records[0]:
        raise _GitFailure(f"git ls-tree returned ambiguous entry for {path}.")
    metadata, listed_path = records[0].split(b"\t", 1)
    fields = metadata.split()
    if len(fields) != 3 or listed_path.decode("utf-8", "replace") != path:
        raise _GitFailure(f"git ls-tree returned malformed entry for {path}.")
    return fields[2].decode("ascii"), _git_bytes(cwd, "show", f"HEAD:{path}")


def _index_entry(cwd: str, path: str) -> tuple[str, bytes] | None:
    listing = _git_bytes(cwd, "ls-files", "--stage", "-z", "--", path)
    if not listing:
        return None
    records = [record for record in listing.split(b"\0") if record]
    if len(records) != 1 or b"\t" not in records[0]:
        raise _GitFailure(f"index has ambiguous or unmerged entry for {path}.")
    metadata, listed_path = records[0].split(b"\t", 1)
    fields = metadata.split()
    if (len(fields) != 3 or fields[2] != b"0" or
            listed_path.decode("utf-8", "replace") != path):
        raise _GitFailure(f"index has malformed or unmerged entry for {path}.")
    return fields[1].decode("ascii"), _git_bytes(cwd, "show", f":{path}")


def _policy_snapshots(cwd: str) -> tuple[dict, dict, dict]:
    baseline_entry = _head_entry(cwd, ".statutor.yaml")
    candidate_entry = _index_entry(cwd, ".statutor.yaml")
    try:
        baseline = (DEFAULT_POLICY if baseline_entry is None else
                    parse_policy(baseline_entry[1], "HEAD:.statutor.yaml"))
    except _PolicyFailure as exc:
        raise _PolicyFailure(
            "HEAD:.statutor.yaml: invalid or unsupported Statutor policy") from exc
    try:
        candidate = (DEFAULT_POLICY if candidate_entry is None else
                     parse_policy(candidate_entry[1], ":.statutor.yaml"))
    except _PolicyFailure as exc:
        raise _PolicyFailure(
            ":.statutor.yaml: invalid or unsupported Statutor policy") from exc
    details = {
        "baseline_policy_oid": baseline_entry[0] if baseline_entry else None,
        "candidate_policy_oid": candidate_entry[0] if candidate_entry else None,
    }
    return baseline, candidate, details


def _reserved_changes(cwd: str, snapshots: dict) -> list[str]:
    """Non-configurable trust-root transitions requiring a receipt."""
    if snapshots["baseline_policy_oid"] is None:
        return []  # first tracked policy is bootstrap; C still judges it
    reserved: list[str] = []
    if snapshots["baseline_policy_oid"] != snapshots["candidate_policy_oid"]:
        reserved.append(".statutor.yaml")

    baseline_bridge = _head_entry(cwd, "CLAUDE.md")
    candidate_bridge = _index_entry(cwd, "CLAUDE.md")
    baseline_blob = baseline_bridge[1] if baseline_bridge else None
    candidate_blob = candidate_bridge[1] if candidate_bridge else None
    baseline_exact = baseline_blob in _EXACT_CLAUDE_BRIDGES
    candidate_exact = candidate_blob in _EXACT_CLAUDE_BRIDGES
    if ((baseline_exact and candidate_blob != baseline_blob) or
            (not baseline_exact and candidate_exact)):
        reserved.append("CLAUDE.md")
    return sorted(reserved)


def _git_local_path(cwd: str, relative: str) -> str:
    raw = _git(cwd, "rev-parse", "--git-path", relative).strip()
    return raw if os.path.isabs(raw) else os.path.abspath(os.path.join(cwd, raw))


def _trust_context(cwd: str, snapshots: dict, reserved: list[str]) -> dict:
    common = _git(cwd, "rev-parse", "--git-common-dir").strip()
    common_path = common if os.path.isabs(common) else os.path.join(cwd, common)
    return {
        "version": _TRUST_RECEIPT_VERSION,
        "repo_identity": os.path.realpath(common_path),
        "head_oid": _head_oid(cwd),
        "index_tree_oid": _git(cwd, "write-tree").strip(),
        "baseline_policy_oid": snapshots["baseline_policy_oid"],
        "candidate_policy_oid": snapshots["candidate_policy_oid"],
        "approved_reserved_paths": reserved,
    }


def _receipt_authorizes(cwd: str, expected: dict) -> bool:
    path = _git_local_path(cwd, "statutor/trust-receipt.json")
    try:
        mode = os.stat(path, follow_symlinks=False).st_mode & 0o777
        if mode != 0o600 or os.path.islink(path):
            return False
        with open(path, encoding="utf-8") as stream:
            receipt = json.load(stream)
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(receipt, dict):
        return False
    if any(receipt.get(key) != value for key, value in expected.items()):
        return False
    return (bool(re.fullmatch(r"D-\d{4,}", receipt.get("decision", ""))) and
            isinstance(receipt.get("reason"), str) and
            bool(receipt["reason"].strip()))


def _policy_change_class(baseline: dict, candidate: dict) -> str:
    if baseline.get("bash_guard", True) and not candidate.get("bash_guard", True):
        return "weakening-or-incomparable"
    old_rules = baseline.get("governed", [])
    new_rules = candidate.get("governed", [])
    pairs = [(r.get("pattern"), r.get("policy")) for r in new_rules]
    if len(set(pairs)) != len(pairs) or len(new_rules) < len(old_rules):
        return "weakening-or-incomparable"
    for old, new in zip(old_rules, new_rules):
        if ((old.get("pattern"), old.get("policy")) !=
                (new.get("pattern"), new.get("policy"))):
            return "weakening-or-incomparable"
        for key in ("max_lines", "hard_max_lines", "soft_max_lines", "stale_after_days"):
            if key in old and (key not in new or new[key] > old[key]):
                return "weakening-or-incomparable"
        if not set(old.get("required_sections", [])).issubset(
                new.get("required_sections", [])):
            return "weakening-or-incomparable"
    return "non-weakening"


def _policy_violations(cwd: str,
                       changes: list[tuple[str, str | None, str | None]],
                       policy: dict) -> list[str]:
    violations: list[str] = []
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
            elif (old_kind in _LIFECYCLE_POLICIES and new_rule is not old_rule):
                violations.append(_lifecycle_reason(old, old_kind, new))
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
            if (code in ("M", "T") or (code == "R" and old_rule is rule)):
                baseline = _git_bytes(cwd, "show", f"HEAD:{old}")
            candidate = _git_bytes(cwd, "show", f":{path}")
            if not _is_pure_line_insertion(baseline, candidate):
                violations.append(
                    f"{path}: append-only, but staged content deletes, rewrites, "
                    "or reorders existing lines. Append superseding records instead.")
        elif kind in ("overwrite_bounded", "constitution"):
            blob = _git_bytes(cwd, "show", f":{path}").decode("utf-8", "replace")
            n = _physical_line_count(blob)
            cap = int(rule.get("max_lines", rule.get("hard_max_lines", 200)))
            if n > cap:
                violations.append(f"{path}: staged version is {n} lines (cap {cap}).")
            missing = [s for s in rule.get("required_sections", []) if s not in blob]
            if missing:
                violations.append(f"{path}: missing sections {missing}.")
        elif kind == "state":
            try:
                candidate = _git_bytes(cwd, "show", f":{path}").decode("utf-8")
            except UnicodeDecodeError:
                violations.append(f"{path}: state content must be valid UTF-8 text.")
                continue
            baseline: str | None = None
            old_rule = _match_rule(old, policy) if old is not None else None
            if (code in ("M", "T") or (code == "R" and old_rule is rule)):
                try:
                    baseline = _git_bytes(cwd, "show", f"HEAD:{old}").decode("utf-8")
                except UnicodeDecodeError:
                    violations.append(f"HEAD:{old}: state content must be valid UTF-8 text.")
                    continue
            reason = _state_reason(path, candidate, baseline)
            if reason:
                violations.append(reason)
    return violations


def run_staged(cwd: str) -> int:
    violations: list[str] = []
    try:
        changes = _staged_changes(cwd)
        baseline, candidate, snapshots = _policy_snapshots(cwd)
        reserved = _reserved_changes(cwd, snapshots)
        if reserved and not _receipt_authorizes(
                cwd, _trust_context(cwd, snapshots, reserved)):
            violations.append(
                "trust-root change requires `statutor trust approve --decision "
                "D-NNNN --reason TEXT`; missing, stale, or unsafe receipt for "
                f"{reserved}.")
        for policy in (baseline, candidate):
            for violation in _policy_violations(cwd, changes, policy):
                if violation not in violations:
                    violations.append(violation)
    except (_GitFailure, _PolicyFailure) as exc:
        print(f"STATUTOR  {exc}")
        return 1

    for violation in violations:
        print(f"STATUTOR  {violation}")
    return 1 if violations else 0


def run_trust_approve(argv: list[str]) -> int:
    """Create the exact-tree local authorization receipt from D-0015."""
    cwd = os.getcwd()
    decision = None
    reason = None
    confirmation = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--decision", "--reason", "--confirm-tree"):
            if i + 1 >= len(argv):
                print(f"missing value for {arg}", file=sys.stderr)
                return 64
            value = argv[i + 1]
            if arg == "--decision":
                decision = value
            elif arg == "--reason":
                reason = value
            else:
                confirmation = value
            i += 2
            continue
        if arg.startswith("-"):
            print(f"unknown option: {arg}", file=sys.stderr)
            return 64
        cwd = arg
        i += 1
    if not decision or not re.fullmatch(r"D-\d{4,}", decision):
        print("--decision D-NNNN is required", file=sys.stderr)
        return 64
    if not reason or not reason.strip():
        print("--reason TEXT is required", file=sys.stderr)
        return 64
    try:
        changes = _staged_changes(cwd)
        baseline, candidate, snapshots = _policy_snapshots(cwd)
        reserved = _reserved_changes(cwd, snapshots)
        if not reserved:
            print("no staged protected trust-root transition to approve", file=sys.stderr)
            return 1
        expected = _trust_context(cwd, snapshots, reserved)
        paths = [new if new is not None else old for _, old, new in changes]
        classification = _policy_change_class(baseline, candidate)
        print(f"classification: {classification}")
        print(f"reserved paths: {', '.join(reserved)}")
        print("staged paths:")
        for path in paths:
            print(f"  {path}")
        diff = _git(cwd, "diff", "--cached", "--", ".statutor.yaml", "CLAUDE.md")
        if diff:
            print(diff, end="" if diff.endswith("\n") else "\n")
        tree = expected["index_tree_oid"]
        print(f"candidate index tree: {tree}")
        if confirmation is None:
            confirmation = input("Type the complete candidate tree ID to approve: ").strip()
        if confirmation != tree:
            print("tree confirmation did not match; no receipt written", file=sys.stderr)
            return 1
        receipt = {
            **expected,
            "decision": decision,
            "reason": reason.strip(),
            "classification": classification,
        }
        path = _git_local_path(cwd, "statutor/trust-receipt.json")
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        temp = path + f".tmp-{os.getpid()}"
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            body = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
            os.write(fd, body)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, path)
        os.chmod(path, 0o600)
        print(f"wrote Git-local trust receipt for tree {tree}")
        return 0
    except (EOFError, OSError, ValueError, _GitFailure, _PolicyFailure) as exc:
        print(f"trust approval failed: {exc}", file=sys.stderr)
        return 1


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
# .statutor.yaml — statutor mutation policy. Embedded defaults apply only
# before a policy is committed (or when the candidate removes it explicitly).
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
    if mode == "trust" and len(argv) > 1 and argv[1] == "approve":
        sys.exit(run_trust_approve(argv[2:]))
    if mode == "init":
        sys.exit(run_init(argv[1] if len(argv) > 1 else os.getcwd()))
    print(__doc__)
    sys.exit(64)


if __name__ == "__main__":
    main()
