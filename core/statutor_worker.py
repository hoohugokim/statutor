#!/usr/bin/env python3
"""Machine-local worker provenance for Statutor v0.5 (D-0020..D-0022, T-0039).

Zero third-party dependencies. Machine identity plus an atomic per-repository
worker registry live under the Statutor XDG state root. This module owns the
local mechanics only: random mode-0600 machine identity, project/worktree
resolution, session leases with expiry, event recording with a strict evidence
vocabulary, compare-and-swap completion baselines, and read-only offline
HANDOFF comparison.

T-0040 extends HANDOFF scaffolds/doctor validation; T-0041 integrates host
adapters and current-release E2E. This module never accepts conversation
content (prompts, tool payloads, diffs, filenames touched, model names,
transcript text) and never contacts the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

import statutor_global as substrate

SCHEMA_VERSION = 1
HARNESSES = ("claude", "codex", "opencode", "custom", "human", "unknown")
ROLES = ("primary", "subagent", "unknown")
EVENTS = ("activity", "attempt", "mutation")
BASES = ("completed", "mutation", "activity", "attempt")
LEASE_TTL = timedelta(hours=24)

# Proven lifecycle surfaces per harness (T-0041). Automatic policy hooks
# (PreToolUse / tool.execute.before) prove an *attempt* only — never a
# confirmed mutation and never completion. No host exposes a post-success
# tool signal or a primary/subagent role fact, so role and origin stay
# `unknown` unless a custom integration proves otherwise. Versions are the
# last verified baselines, not live probes.
CAPABILITIES: dict[str, dict[str, object]] = {
    "claude": {
        "verified_against": "Claude Code 2.1.258",
        "attempt_surface": "PreToolUse hook (Write|Edit|Bash|apply_patch)",
        "proves": ["activity", "attempt"],
        "proves_mutation": False,
        "proves_completion": False,
        "role_signal": False,
        "session_correlation": "host session id when exposed, else generated",
        "note": "Stop hook surfaces drift only; completion is executor-run "
                "`worker complete`.",
    },
    "codex": {
        "verified_against": "Codex CLI 0.152.1",
        "attempt_surface": "PreToolUse hook (Bash|apply_patch matchers)",
        "proves": ["activity", "attempt"],
        "proves_mutation": False,
        "proves_completion": False,
        "role_signal": False,
        "session_correlation": "host session id when exposed, else generated",
        "note": "Bash is the only fully interceptable tool; MCP tool ids "
                "never reach the hook — the git floor covers them.",
    },
    "opencode": {
        "verified_against": "OpenCode 1.18.20",
        "attempt_surface": "tool.execute.before (write|edit|bash|apply_patch)",
        "proves": ["activity", "attempt"],
        "proves_mutation": False,
        "proves_completion": False,
        "role_signal": False,
        "session_correlation": "plugin sessionID; no primary/subagent "
                               "distinction is exposed",
        "note": "Subagent tool calls fire the same hooks; server-namespaced "
                "MCP tool ids never match the allowlist.",
    },
    "custom": {
        "verified_against": "n/a (caller-proved)",
        "attempt_surface": "`worker record` CLI ingress",
        "proves": ["activity", "attempt", "mutation"],
        "proves_mutation": True,
        "proves_completion": False,
        "role_signal": True,
        "session_correlation": "caller-supplied --session id",
        "note": "A custom harness may record mutation only through a "
                "post-success surface it operates; Statutor takes the "
                "caller's word for the evidence basis.",
    },
    "human": {
        "verified_against": "n/a",
        "attempt_surface": "direct CLI use",
        "proves": ["activity", "attempt", "mutation"],
        "proves_mutation": True,
        "proves_completion": False,
        "role_signal": True,
        "session_correlation": "caller-supplied --session id",
        "note": "Completion is still recorded only via `worker complete` "
                "against a valid HANDOFF.",
    },
    "unknown": {
        "verified_against": "n/a",
        "attempt_surface": "none declared",
        "proves": ["activity"],
        "proves_mutation": False,
        "proves_completion": False,
        "role_signal": False,
        "session_correlation": "generated session id",
        "note": "Unknown means unproven, never a fallback guess.",
    },
}


def host_capabilities(harness: str) -> dict[str, object]:
    _check_harness(harness)
    return {"harness": harness, **CAPABILITIES[harness]}


def all_capabilities() -> dict[str, object]:
    return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
            "capabilities": {name: {"harness": name, **caps}
                             for name, caps in CAPABILITIES.items()},
            "note": "Static declarations of proven surfaces; automatic "
                    "policy hooks prove attempt only on every host."}
SESSION_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")
HEX32_RE = re.compile(r"[0-9a-f]{32}")
LABEL_MAX = 128


class WorkerError(substrate.GlobalError):
    """Base error for worker-provenance failures."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _machine_path(state_root: Path) -> Path:
    return Path(state_root) / "machine.json"


def _project_dir(state_root: Path, project_id: str) -> Path:
    return Path(state_root) / "projects" / project_id


def _registry_path(state_root: Path, project_id: str) -> Path:
    return _project_dir(state_root, project_id) / "workers.json"


def validate_machine(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise WorkerError("machine identity must be a JSON object")
    keys = set(data)
    if keys != {"schema_version", "machine_id", "created_at", "label",
                "label_updated_at"}:
        raise WorkerError("machine identity has unexpected keys")
    if data["schema_version"] != SCHEMA_VERSION:
        raise WorkerError("unsupported machine schema")
    if not isinstance(data["machine_id"], str) or not HEX32_RE.fullmatch(
            data["machine_id"]):
        raise WorkerError("machine identity has an invalid machine_id")
    if _parse_time(data["created_at"]) is None:
        raise WorkerError("machine identity has an invalid created_at")
    label = data["label"]
    if label is not None and (not isinstance(label, str) or not label.strip()
                              or len(label) > LABEL_MAX):
        raise WorkerError("machine label must be 1-128 chars or null")
    if data["label_updated_at"] is not None and _parse_time(
            data["label_updated_at"]) is None:
        raise WorkerError("machine identity has an invalid label_updated_at")
    return data


def default_machine_doc(machine_id: str, created_at: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "machine_id": machine_id,
        "created_at": created_at,
        "label": None,
        "label_updated_at": None,
    }


def _read_machine_locked(path: Path) -> dict[str, object] | None:
    if path.is_file():
        return validate_machine(substrate.load_json(path))
    return None


def ensure_machine(state_root: Path) -> tuple[dict[str, object], bool]:
    """Create the random machine identity on first use (mode 0600)."""
    root = substrate._absolute(state_root)
    path = _machine_path(root)
    if path.is_file():
        doc = validate_machine(substrate.load_json(path))
        return doc, False
    with substrate.StateLock(root):
        existing = _read_machine_locked(path)
        if existing is not None:
            return existing, False
        doc = default_machine_doc(secrets.token_hex(16), _iso(_now()))
        validate_machine(doc)
        substrate.atomic_write_json(path, doc, expected=substrate.ABSENT,
                                    mode=0o600)
        return doc, True


def show_machine(state_root: Path) -> dict[str, object]:
    doc, _ = ensure_machine(state_root)
    return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
            "machine": doc}


def set_machine_label(state_root: Path, label: str) -> dict[str, object]:
    if not label.strip() or len(label) > LABEL_MAX:
        raise WorkerError("label must be 1-128 chars")
    root = substrate._absolute(Path(state_root))
    with substrate.StateLock(root):
        doc = _read_machine_locked(_machine_path(root))
        if doc is None:
            doc = default_machine_doc(secrets.token_hex(16), _iso(_now()))
            substrate.atomic_write_json(_machine_path(root), doc,
                                        expected=substrate.ABSENT, mode=0o600)
        before = substrate.fingerprint(_machine_path(root)).token
        updated = dict(doc)
        updated["label"] = label.strip()
        updated["label_updated_at"] = _iso(_now())
        validate_machine(updated)
        substrate.atomic_write_json(_machine_path(root), updated,
                                    expected=before, mode=0o600)
        return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
                "machine": updated}


def rotate_machine(state_root: Path, *, confirm: bool = False) -> dict[str, object]:
    if not confirm:
        raise WorkerError("rotation requires explicit confirmation")
    root = substrate._absolute(Path(state_root))
    with substrate.StateLock(root):
        doc = _read_machine_locked(_machine_path(root))
        if doc is None:
            doc = default_machine_doc(secrets.token_hex(16), _iso(_now()))
            substrate.atomic_write_json(_machine_path(root), doc,
                                        expected=substrate.ABSENT, mode=0o600)
        before = substrate.fingerprint(_machine_path(root)).token
        updated = default_machine_doc(secrets.token_hex(16), _iso(_now()))
        updated["label"] = None
        updated["label_updated_at"] = None
        validate_machine(updated)
        if updated["machine_id"] == doc["machine_id"]:
            raise WorkerError("rotation produced a duplicate id; retry")
        substrate.atomic_write_json(_machine_path(root), updated,
                                    expected=before, mode=0o600)
        return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
                "previous_machine_id": doc["machine_id"], "machine": updated}


# --------------------------------------------------------------------------
# git + ledger helpers (tolerant: unknown rather than inferred/guessed)
# --------------------------------------------------------------------------

def _git_optional(cwd: str, *args: str) -> str | None:
    raw = _git_bytes_optional(cwd, *args)
    if raw is None:
        return None
    return raw.decode("utf-8", "replace").strip()


def _git_bytes_optional(cwd: str, *args: str) -> bytes | None:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                                check=False, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _resolve_project(cwd: str) -> tuple[str, str, str]:
    """Return (project_id, derivation, repository_display)."""
    common = _git_optional(cwd, "rev-parse", "--git-common-dir")
    if common is not None:
        if not os.path.isabs(common):
            common = os.path.abspath(os.path.join(cwd, common))
        real = os.path.realpath(common)
        digest = hashlib.sha256(real.encode("utf-8")).hexdigest()[:32]
        return digest, "git-common", real
    from statutor_core import find_ledger_root  # deferred: avoids import cycle
    ledger = find_ledger_root(cwd)
    if ledger is None:
        raise WorkerError("worker state requires a Git repository or a "
                          "marked ledger (.statutor.yaml)")
    real = os.path.realpath(os.path.abspath(ledger))
    digest = hashlib.sha256(("ledger:" + real).encode("utf-8")).hexdigest()[:32]
    return digest, "ledger-root", real


def _resolve_worktree(cwd: str) -> str:
    top = _git_optional(cwd, "rev-parse", "--show-toplevel")
    if top:
        return os.path.realpath(os.path.abspath(top))
    return os.path.realpath(os.path.abspath(cwd))


def _worktree_id(worktree_root: str) -> str:
    return hashlib.sha256(worktree_root.encode("utf-8")).hexdigest()[:16]


def _head_oid(cwd: str) -> str | None:
    out = _git_optional(cwd, "rev-parse", "--verify", "--quiet", "HEAD")
    return out if out else None


# --------------------------------------------------------------------------
# HANDOFF parsing (tolerant; T-0040 adds scaffold + doctor validation)
# --------------------------------------------------------------------------

_FIELD_RES = {
    # NOTE: horizontal whitespace only around the value — `\s` would eat
    # newlines and capture across lines on an empty-valued key.
    name: re.compile(rf"^{name}:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)
    for name in ("last_verified", "last_worker", "last_machine",
                 "last_machine_label", "handoff_id", "supersedes")
}
ATTRIBUTION_FIELDS = ("last_worker", "last_machine", "handoff_id",
                      "supersedes")
HANDOFF_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")


def validate_handoff_metadata(text: str) -> list[str]:
    """Shape-check the optional v0.5 HANDOFF attribution block.

    Returns diagnostics (empty = absent or valid). Absent fields carry
    unknown/none semantics, so partial blocks are tolerated and old ledgers
    without any block remain valid. Shared by the doctor and completion
    validation so both judge the same shapes.
    """
    fields = parse_handoff_fields(text)
    if all(fields[name] is None for name in ATTRIBUTION_FIELDS):
        return []
    problems: list[str] = []
    if fields["last_worker"] is not None \
            and fields["last_worker"] not in HARNESSES:
        problems.append(
            f"last_worker {fields['last_worker']!r} is not a stable harness "
            f"id (expected one of {', '.join(HARNESSES)})")
    if fields["last_machine"] is not None \
            and fields["last_machine"] != "unknown" \
            and not HEX32_RE.fullmatch(fields["last_machine"]):
        problems.append(
            f"last_machine {fields['last_machine']!r} is neither 'unknown' "
            "nor a 32-hex machine id")
    if fields["handoff_id"] is not None \
            and fields["handoff_id"] != "none" \
            and not HANDOFF_ID_RE.fullmatch(fields["handoff_id"]):
        problems.append(
            f"handoff_id {fields['handoff_id']!r} is neither 'none' nor a "
            "token of [A-Za-z0-9._-]{1,128}")
    if fields["supersedes"] is not None \
            and fields["supersedes"] != "none":
        names = [part.strip() for part in fields["supersedes"].split(",")]
        if not names or any(not HANDOFF_ID_RE.fullmatch(part)
                            for part in names):
            problems.append(
                f"supersedes {fields['supersedes']!r} is neither 'none' nor "
                "a comma-separated list of handoff id tokens")
    label = fields["last_machine_label"]
    if label is not None and (not label.strip() or len(label) > LABEL_MAX):
        problems.append("last_machine_label must be 1-128 chars when present")
    elif label is None and re.search(r"^last_machine_label:\s*$", text,
                                     re.MULTILINE):
        problems.append("last_machine_label must be 1-128 chars when present")
    return problems


def parse_handoff_fields(text: str) -> dict[str, str | None]:
    fields: dict[str, str | None] = {}
    for name, pattern in _FIELD_RES.items():
        match = pattern.search(text)
        fields[name] = match.group(1).strip() if match else None
    return fields


def _read_handoff_text(ledger_root: str | None, cwd: str,
                       ref: str | None = None) -> tuple[str | None, str | None]:
    """Return (digest, text) for the worktree file or a git ref blob."""
    if ref is None:
        if ledger_root is None:
            return None, None
        path = Path(ledger_root) / "HANDOFF.md"
        try:
            content = path.read_bytes()
        except OSError:
            return None, None
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        try:
            return digest, content.decode("utf-8")
        except UnicodeDecodeError:
            return digest, None
    raw = _git_bytes_optional(cwd, "show", f"{ref}:HANDOFF.md")
    # NOTE: bare `git show REF:HANDOFF.md` resolves from the repo root, but a
    # ledger may live in a subdirectory; fall back to the ledger-relative path.
    if raw is None and ledger_root is not None:
        try:
            rel = os.path.relpath(os.path.join(ledger_root, "HANDOFF.md"),
                                  _resolve_worktree(cwd))
        except ValueError:
            rel = "HANDOFF.md"
        raw = _git_bytes_optional(cwd, "show", f"{ref}:{rel}")
    if raw is None:
        return None, None
    # Hash the exact blob bytes so worktree and ref digests agree even for
    # non-UTF-8 files; parse from a strict decode (None when undecodable,
    # mirroring the worktree branch above).
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    try:
        return digest, raw.decode("utf-8")
    except UnicodeDecodeError:
        return digest, None


def read_handoff(ledger_root: str | None, cwd: str,
                 ref: str | None = None) -> tuple[str | None, str | None]:
    """Return (digest, handoff_id) for the worktree file or a git ref blob."""
    digest, text = _read_handoff_text(ledger_root, cwd, ref)
    if digest is None or text is None:
        return digest, None
    return digest, parse_handoff_fields(text)["handoff_id"]


def _attribution_summary(text: str | None) -> dict[str, object]:
    """Portable worker/machine attribution with unknown defaults.

    The label is caller-controlled display metadata: surfaced as data (never
    rendered where an id is expected), null when the block omits it.
    """
    fields = parse_handoff_fields(text) if text is not None else {}
    return {
        "last_worker": str(fields.get("last_worker") or "unknown"),
        "last_machine": str(fields.get("last_machine") or "unknown"),
        "last_machine_label": fields.get("last_machine_label"),
        "handoff_id": str(fields.get("handoff_id") or "none"),
    }


# --------------------------------------------------------------------------
# registry schema
# --------------------------------------------------------------------------

def _empty_basis() -> dict[str, object | None]:
    return {"activity": None, "attempt": None, "mutation": None,
            "completed": None}


def _validate_record(data: object, label: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise WorkerError(f"{label} must be an object")
    expected = {"harness", "role", "origin_harness", "machine_id",
                "machine_label", "timestamp", "session_id", "scope",
                "evidence", "handoff_id"}
    if set(data) != expected:
        raise WorkerError(f"{label} has unexpected keys")
    if data["harness"] not in HARNESSES:
        raise WorkerError(f"{label} has an invalid harness")
    if data["role"] not in ROLES:
        raise WorkerError(f"{label} has an invalid role")
    if data["origin_harness"] not in HARNESSES:
        raise WorkerError(f"{label} has an invalid origin_harness")
    if not isinstance(data["machine_id"], str) or not HEX32_RE.fullmatch(
            data["machine_id"]):
        raise WorkerError(f"{label} has an invalid machine_id")
    if data["machine_label"] is not None and not isinstance(
            data["machine_label"], str):
        raise WorkerError(f"{label} has an invalid machine_label")
    if _parse_time(data["timestamp"]) is None:
        raise WorkerError(f"{label} has an invalid timestamp")
    if not isinstance(data["session_id"], str) or not SESSION_RE.fullmatch(
            data["session_id"]):
        raise WorkerError(f"{label} has an invalid session_id")
    if data["scope"] != "machine-local":
        raise WorkerError(f"{label} scope must be machine-local")
    if not isinstance(data["evidence"], str) or not data["evidence"]:
        raise WorkerError(f"{label} has invalid evidence")
    if data["handoff_id"] is not None and not isinstance(data["handoff_id"],
                                                         str):
        raise WorkerError(f"{label} has an invalid handoff_id")
    return data


def validate_registry(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise WorkerError("worker registry must be a JSON object")
    if set(data) != {"schema_version", "project_id", "derivation",
                     "repository_display", "updated_at", "worktrees",
                     "sessions"}:
        raise WorkerError("worker registry has unexpected keys")
    if data["schema_version"] != SCHEMA_VERSION:
        raise WorkerError("unsupported worker registry schema")
    if not isinstance(data["project_id"], str) or not re.fullmatch(
            r"[0-9a-f]{32}", data["project_id"]):
        raise WorkerError("worker registry has an invalid project_id")
    if data["derivation"] not in ("git-common", "ledger-root"):
        raise WorkerError("worker registry has an invalid derivation")
    if _parse_time(data["updated_at"]) is None:
        raise WorkerError("worker registry has an invalid updated_at")
    if not isinstance(data["worktrees"], dict):
        raise WorkerError("worker registry worktrees must be an object")
    for wt_id, wt in data["worktrees"].items():
        if not isinstance(wt, dict) or set(wt) != {
                "worktree_root", "latest", "per_harness", "leases"}:
            raise WorkerError("worker registry has an invalid worktree entry")
        latest = wt["latest"]
        if not isinstance(latest, dict) or set(latest) != {
                "activity", "attempt", "mutation", "completed"}:
            raise WorkerError("worker registry has invalid latest pointers")
        for basis, record in latest.items():
            if record is not None:
                _validate_record(record, f"latest.{basis}")
        if not isinstance(wt["per_harness"], dict):
            raise WorkerError("per_harness must be an object")
        for harness, buckets in wt["per_harness"].items():
            if harness not in HARNESSES:
                raise WorkerError("per_harness has an invalid harness")
            if not isinstance(buckets, dict) or set(buckets) != {
                    "activity", "attempt", "mutation", "completed"}:
                raise WorkerError("per_harness buckets are invalid")
            for basis, record in buckets.items():
                if record is not None:
                    _validate_record(record, f"per_harness.{harness}.{basis}")
        if not isinstance(wt["leases"], list):
            raise WorkerError("leases must be a list")
        for lease in wt["leases"]:
            if not isinstance(lease, dict) or set(lease) != {
                    "session_id", "harness", "started_at", "expires_at",
                    "worktree_id"}:
                raise WorkerError("lease entry is invalid")
    if not isinstance(data["sessions"], dict):
        raise WorkerError("worker registry sessions must be an object")
    for sid, session in data["sessions"].items():
        if not isinstance(session, dict) or set(session) != {
                "session_id", "harness", "role", "origin_harness",
                "machine_id", "machine_label", "worktree_id",
                "worktree_root", "started_at", "expires_at",
                "baseline_head", "baseline_handoff_digest",
                "baseline_handoff_id", "status"}:
            raise WorkerError("worker registry has an invalid session")
        if session["status"] not in ("active", "completed", "expired"):
            raise WorkerError("session has an invalid status")
    return data


def _new_registry(project_id: str, derivation: str,
                  display: str) -> dict[str, object]:
    return {"schema_version": SCHEMA_VERSION, "project_id": project_id,
            "derivation": derivation, "repository_display": display,
            "updated_at": _iso(_now()), "worktrees": {}, "sessions": {}}


def _ensure_worktree(registry: dict[str, object], wt_id: str,
                     wt_root: str) -> dict[str, object]:
    worktrees = registry["worktrees"]
    assert isinstance(worktrees, dict)
    entry = worktrees.get(wt_id)
    if not isinstance(entry, dict):
        entry = {"worktree_root": wt_root, "latest": _empty_basis(),
                 "per_harness": {}, "leases": []}
        worktrees[wt_id] = entry
    return entry


class _ProjectLock:
    """Bounded mkdir lock scoped to one project directory.

    Like substrate.StateLock, stale locks (kill -9 between acquire and
    release) require explicit recovery: remove `<project-dir>/.worker.lock`
    (rmdir fails while held, so a present lock is either live or stale —
    confirm no statutor process is running before removing).
    """

    def __init__(self, project_dir: Path):
        self.path = project_dir / ".worker.lock"
        self.acquired = False

    def __enter__(self) -> "_ProjectLock":
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.path.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise WorkerError(
                f"worker registry lock is busy: {self.path}") from exc
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.acquired:
            try:
                self.path.rmdir()
            except OSError:
                pass
            self.acquired = False


def _load_or_init(state_root: Path, project_id: str, derivation: str,
                  display: str) -> tuple[dict[str, object], str]:
    path = _registry_path(state_root, project_id)
    if path.is_file():
        registry = validate_registry(substrate.load_json(path))
        if registry["project_id"] != project_id:
            raise WorkerError("worker registry project mismatch")
        token = substrate.fingerprint(path).token
        return registry, token
    return _new_registry(project_id, derivation, display), substrate.ABSENT


def _store(state_root: Path, project_id: str,
           registry: dict[str, object], expected: str) -> None:
    validate_registry(registry)
    registry["updated_at"] = _iso(_now())
    # Prune leases/sessions to bounded size: keep 50 sessions, 20 leases/wt.
    sessions = registry["sessions"]
    assert isinstance(sessions, dict)
    if len(sessions) > 50:
        ordered = sorted(sessions.items(),
                         key=lambda kv: str(kv[1].get("started_at", "")))
        for sid, _ in ordered[:len(sessions) - 50]:
            del sessions[sid]
    worktrees = registry["worktrees"]
    assert isinstance(worktrees, dict)
    for wt in worktrees.values():
        assert isinstance(wt, dict)
        leases = wt["leases"]
        assert isinstance(leases, list)
        if len(leases) > 20:
            leases.sort(key=lambda item: str(item.get("started_at", "")))
            del leases[:len(leases) - 20]
    substrate.atomic_write_json(_registry_path(state_root, project_id),
                                registry, expected=expected, mode=0o600)


def _prune_expired(registry: dict[str, object]) -> None:
    now = _now()
    sessions = registry["sessions"]
    assert isinstance(sessions, dict)
    for session in sessions.values():
        assert isinstance(session, dict)
        expires = _parse_time(session.get("expires_at"))
        if session.get("status") == "active" and expires is not None \
                and expires <= now:
            session["status"] = "expired"
    worktrees = registry["worktrees"]
    assert isinstance(worktrees, dict)
    for wt in worktrees.values():
        assert isinstance(wt, dict)
        leases = wt["leases"]
        assert isinstance(leases, list)
        kept = []
        for lease in leases:
            expires = _parse_time(lease.get("expires_at"))
            if expires is not None and expires > now:
                kept.append(lease)
            else:
                sid = lease.get("session_id")
                if isinstance(sid, str) and sid in sessions:
                    existing = sessions[sid]
                    if isinstance(existing, dict) and existing.get(
                            "status") == "active":
                        existing["status"] = "expired"
        wt["leases"] = kept


def _check_harness(harness: str) -> str:
    if harness not in HARNESSES:
        raise WorkerError(f"unsupported harness: {harness}")
    return harness


def _check_role(role: str) -> str:
    if role not in ROLES:
        raise WorkerError(f"unsupported role: {role}")
    return role


def _require_ledger(cwd: str) -> str:
    from statutor_core import find_ledger_root  # deferred: avoids import cycle
    ledger = find_ledger_root(cwd)
    if ledger is None:
        raise WorkerError("worker ingress requires a marked ledger "
                          "(.statutor.yaml); nothing changed")
    return ledger


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def worker_begin(state_root: Path, cwd: str, *, harness: str,
                 role: str = "unknown",
                 origin_harness: str = "unknown",
                 session_id: str | None = None) -> dict[str, object]:
    _check_harness(harness)
    _check_role(role)
    if origin_harness not in HARNESSES:
        raise WorkerError(f"unsupported origin_harness: {origin_harness}")
    ledger = _require_ledger(cwd)
    machine, _ = ensure_machine(state_root)
    project_id, derivation, display = _resolve_project(cwd)
    wt_root = _resolve_worktree(cwd)
    wt_id = _worktree_id(wt_root)
    head = _head_oid(cwd)
    digest, handoff_id = read_handoff(ledger, cwd)
    sid = session_id or secrets.token_hex(16)
    if not SESSION_RE.fullmatch(sid):
        raise WorkerError("invalid session id")
    now = _now()
    session = {
        "session_id": sid, "harness": harness, "role": role,
        "origin_harness": origin_harness, "machine_id": machine["machine_id"],
        "machine_label": machine["label"], "worktree_id": wt_id,
        "worktree_root": wt_root, "started_at": _iso(now),
        "expires_at": _iso(now + LEASE_TTL), "baseline_head": head,
        # Diagnostic only: CAS binds handoff_id lineage (plus supersedes,
        # machine, worker), never the digest — every legitimate rewrite
        # changes the body, so digest equality would reject valid work.
        "baseline_handoff_digest": digest,
        "baseline_handoff_id": handoff_id if handoff_id else "none",
        "status": "active",
    }
    with _ProjectLock(_project_dir(state_root, project_id)):
        registry, expected = _load_or_init(state_root, project_id, derivation,
                                           display)
        _prune_expired(registry)
        sessions = registry["sessions"]
        assert isinstance(sessions, dict)
        if sid in sessions:
            raise WorkerError(f"session already exists: {sid}")
        sessions[sid] = session
        entry = _ensure_worktree(registry, wt_id, wt_root)
        leases = entry["leases"]
        assert isinstance(leases, list)
        leases.append({"session_id": sid, "harness": harness,
                       "started_at": _iso(now),
                       "expires_at": _iso(now + LEASE_TTL),
                       "worktree_id": wt_id})
        _store(state_root, project_id, registry, expected)
    return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
            "operation": "worker-begin", "project_id": project_id,
            "derivation": derivation, "worktree_id": wt_id,
            "worktree_root": wt_root, "ledger_root": ledger,
            "session": session,
            "capabilities": host_capabilities(harness),
            "capability_note": "begin proves activity only, never mutation; "
                               "see `worker capabilities` for proven surfaces"}


def _touch(registry: dict[str, object], wt_id: str, wt_root: str, *,
           event: str, harness: str, role: str, origin_harness: str,
           machine: dict[str, object], session_id: str,
           handoff_id: str | None) -> dict[str, object]:
    record = {"harness": harness, "role": role,
              "origin_harness": origin_harness,
              "machine_id": machine["machine_id"],
              "machine_label": machine["label"],
              "timestamp": _iso(_now()), "session_id": session_id,
              "scope": "machine-local",
              "evidence": event if event != "activity" else "begin",
              "handoff_id": handoff_id}
    _validate_record(record, "record")
    entry = _ensure_worktree(registry, wt_id, wt_root)
    latest = entry["latest"]
    assert isinstance(latest, dict)
    latest[event] = record
    per = entry["per_harness"]
    assert isinstance(per, dict)
    buckets = per.get(harness)
    if not isinstance(buckets, dict):
        buckets = {"activity": None, "attempt": None, "mutation": None,
                   "completed": None}
        per[harness] = buckets
    buckets[event] = record
    return record


def worker_record(state_root: Path, cwd: str, *, harness: str, event: str,
                  role: str = "unknown", origin_harness: str = "unknown",
                  session_id: str | None = None) -> dict[str, object]:
    _check_harness(harness)
    if event not in EVENTS:
        raise WorkerError(f"unsupported event: {event} "
                          f"(expected one of {', '.join(EVENTS)})")
    _check_role(role)
    if origin_harness not in HARNESSES:
        raise WorkerError(f"unsupported origin_harness: {origin_harness}")
    ledger = _require_ledger(cwd)
    if event == "mutation" and harness in ("claude", "codex", "opencode"):
        # PreToolUse/tool-before proves an attempt, never a confirmed
        # mutation; automatic adapters must not record mutation directly.
        raise WorkerError("automatic harnesses prove attempt, never mutation; "
                          "mutation requires a post-success surface")
    machine, _ = ensure_machine(state_root)
    project_id, derivation, display = _resolve_project(cwd)
    wt_root = _resolve_worktree(cwd)
    wt_id = _worktree_id(wt_root)
    _, current_handoff = read_handoff(ledger, cwd)
    with _ProjectLock(_project_dir(state_root, project_id)):
        registry, expected = _load_or_init(state_root, project_id, derivation,
                                           display)
        _prune_expired(registry)
        sid = session_id
        if sid is not None:
            sessions = registry["sessions"]
            assert isinstance(sessions, dict)
            if sid not in sessions:
                raise WorkerError(f"unknown session: {sid}")
        else:
            sid = f"manual-{secrets.token_hex(8)}"
        record = _touch(registry, wt_id, wt_root, event=event, harness=harness,
                        role=role, origin_harness=origin_harness,
                        machine=machine, session_id=sid,
                        handoff_id=current_handoff if current_handoff else "none")
        if session_id is not None:
            sessions = registry["sessions"]
            assert isinstance(sessions, dict)
            session = sessions.get(session_id)
            if isinstance(session, dict) and session.get("status") == "active":
                session["expires_at"] = _iso(_now() + LEASE_TTL)
                entry = _ensure_worktree(registry, wt_id, wt_root)
                leases = entry["leases"]
                assert isinstance(leases, list)
                for lease in leases:
                    if lease.get("session_id") == session_id:
                        lease["expires_at"] = session["expires_at"]
        _store(state_root, project_id, registry, expected)
    return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
            "operation": "worker-record", "project_id": project_id,
            "worktree_id": wt_id, "record": record}


def _aggregate_latest(registry: dict[str, object], basis: str,
                      wt_id: str | None) -> dict[str, object] | None:
    if basis not in BASES:
        raise WorkerError(f"unsupported basis: {basis}")
    worktrees = registry["worktrees"]
    assert isinstance(worktrees, dict)
    candidates: list[dict[str, object]] = []
    for candidate_id, wt in worktrees.items():
        if wt_id is not None and candidate_id != wt_id:
            continue
        assert isinstance(wt, dict)
        latest = wt["latest"]
        assert isinstance(latest, dict)
        record = latest.get(basis)
        if isinstance(record, dict):
            candidates.append(record)
    if not candidates:
        return None
    candidates.sort(key=lambda item: str(item.get("timestamp", "")))
    return candidates[-1]


def worker_show(state_root: Path, cwd: str, *, basis: str = "completed",
                worktree_only: bool = False) -> dict[str, object]:
    project_id, _, _ = _resolve_project(cwd)
    path = _registry_path(state_root, project_id)
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
                "basis": basis, "worktree_only": worktree_only,
                "project_id": project_id, "record": None,
                "note": "unknown: no local worker state"}
    registry = validate_registry(substrate.load_json(path))
    _prune_expired(registry)
    wt_id = _worktree_id(_resolve_worktree(cwd)) if worktree_only else None
    record = _aggregate_latest(registry, basis, wt_id)
    return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
            "basis": basis, "worktree_only": worktree_only,
            "project_id": project_id, "record": record}


def worker_active(state_root: Path, cwd: str,
                  *, worktree_only: bool = False) -> dict[str, object]:
    project_id, _, _ = _resolve_project(cwd)
    path = _registry_path(state_root, project_id)
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
                "project_id": project_id, "leases": []}
    registry = validate_registry(substrate.load_json(path))
    _prune_expired(registry)
    wt_filter = _worktree_id(_resolve_worktree(cwd)) if worktree_only else None
    worktrees = registry["worktrees"]
    assert isinstance(worktrees, dict)
    leases = []
    for wt_id, wt in worktrees.items():
        if wt_filter is not None and wt_id != wt_filter:
            continue
        assert isinstance(wt, dict)
        entry_leases = wt["leases"]
        assert isinstance(entry_leases, list)
        for lease in entry_leases:
            leases.append({**lease, "worktree_root": wt.get("worktree_root")})
    leases.sort(key=lambda item: str(item.get("started_at", "")))
    return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
            "project_id": project_id, "leases": leases,
            "note": "leases are machine-local presence hints, never proof "
                    "of useful work"}


def worker_complete(state_root: Path, cwd: str, *,
                    session_id: str) -> dict[str, object]:
    if not SESSION_RE.fullmatch(session_id):
        raise WorkerError("invalid session id")
    ledger = _require_ledger(cwd)
    machine, _ = ensure_machine(state_root)
    project_id, derivation, display = _resolve_project(cwd)
    wt_root = _resolve_worktree(cwd)
    wt_id = _worktree_id(wt_root)
    current_digest, current_handoff = read_handoff(ledger, cwd)
    if current_digest is None:
        raise WorkerError("completion requires a HANDOFF.md in the ledger")
    current_id = current_handoff if current_handoff else "none"
    ledger_path = Path(ledger) / "HANDOFF.md"
    try:
        handoff_text = ledger_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkerError(f"cannot read HANDOFF.md: {exc}") from exc
    shape_problems = validate_handoff_metadata(handoff_text)
    if shape_problems:
        raise WorkerError("HANDOFF attribution block is malformed: "
                          + "; ".join(shape_problems))
    handoff_fields = parse_handoff_fields(handoff_text)
    with _ProjectLock(_project_dir(state_root, project_id)):
        registry, expected = _load_or_init(state_root, project_id, derivation,
                                           display)
        _prune_expired(registry)
        sessions = registry["sessions"]
        assert isinstance(sessions, dict)
        session = sessions.get(session_id)
        if not isinstance(session, dict):
            raise WorkerError(f"unknown session: {session_id}")
        baseline = str(session.get("baseline_handoff_id", "none"))
        entry = _ensure_worktree(registry, wt_id, wt_root)
        latest = entry["latest"]
        assert isinstance(latest, dict)
        prior = latest.get("completed")
        prior_id = str(prior.get("handoff_id", "none")) if isinstance(
            prior, dict) else "none"
        supersedes = handoff_fields.get("supersedes")
        names = {part.strip() for part in (supersedes or "").split(",")
                 if part.strip()} if supersedes else set()
        fresh = current_id != "none" and current_id != baseline \
            and current_id != prior_id
        reconciled: list[str] | None = None
        if prior_id == baseline or prior_id == "none":
            # Normal path, including first completion from an attributed
            # baseline: no local session completed ahead of us.
            pass
        elif baseline in names and prior_id in names and fresh:
            # Same-machine reconciliation: the executor absorbed both the
            # session baseline and the locally completed sibling into one
            # fresh HANDOFF. Only this restores a linear current state.
            reconciled = sorted({baseline, prior_id} - {"none"})
        else:
            raise WorkerError(
                "completion CAS failed: another local session completed "
                f"first (baseline {baseline}, current completed {prior_id} "
                f"by {prior.get('harness')}/{prior.get('machine_id')}/"
                f"{prior.get('session_id')}); reconcile both ids into one "
                "fresh HANDOFF naming them in supersedes before completing")
        claimed_machine = handoff_fields.get("last_machine")
        if claimed_machine not in (None, "unknown") \
                and claimed_machine != machine["machine_id"]:
            raise WorkerError(
                "HANDOFF last_machine "
                f"{claimed_machine!r} does not match this machine "
                f"({machine['machine_id']}); the rewrite attributes another "
                "machine — fix the attribution before completing")
        claimed_worker = handoff_fields.get("last_worker")
        session_harness = str(session.get("harness", "unknown"))
        if claimed_worker not in (None, "unknown") \
                and claimed_worker != session_harness:
            raise WorkerError(
                f"HANDOFF last_worker {claimed_worker!r} does not match the "
                f"session harness ({session_harness}); fix the attribution "
                "before completing")
        if baseline != "none" and reconciled is None:
            if current_id == baseline:
                raise WorkerError(
                    "completion requires a fresh handoff_id distinct from "
                    f"the session baseline ({baseline})")
            # Verify the rewritten HANDOFF names its baseline. Tolerant of
            # legacy files without supersedes only when baseline is none.
            if baseline not in names:
                raise WorkerError(
                    f"completion requires supersedes naming {baseline}; "
                    f"found {supersedes!r}")
        record = _touch(registry, wt_id, wt_root, event="completed",
                        harness=str(session.get("harness", "unknown")),
                        role=str(session.get("role", "unknown")),
                        origin_harness=str(session.get("origin_harness",
                                                       "unknown")),
                        machine=machine, session_id=session_id,
                        handoff_id=current_id)
        record["evidence"] = "completed"
        latest["completed"] = record
        per = entry["per_harness"]
        assert isinstance(per, dict)
        buckets = per.get(record["harness"])
        if isinstance(buckets, dict):
            buckets["completed"] = record
        session["status"] = "completed"
        # Purge the completed lease; crashed sessions age out via expiry.
        leases = entry["leases"]
        assert isinstance(leases, list)
        entry["leases"] = [lease for lease in leases
                           if lease.get("session_id") != session_id]
        _store(state_root, project_id, registry, expected)
    return {"schema_version": SCHEMA_VERSION, "scope": "machine-local",
            "operation": "worker-complete", "project_id": project_id,
            "worktree_id": wt_id, "record": record,
            "reconciled": reconciled,
            "handoff_digest": current_digest}


def worker_compare(state_root: Path, cwd: str,
                   *, ref: str) -> dict[str, object]:
    # No legitimate ref starts with `-`; without this guard the value below
    # reaches `git merge-base`/`git show` argv as an option flag. Git fails
    # safe today, but comparison must never hand option-shaped input to git.
    if not ref or ref.startswith("-") or re.search(r"[\s~^:?*\[\\]", ref):
        raise WorkerError("invalid git ref")
    ledger = _require_ledger(cwd)
    base = _git_optional(cwd, "merge-base", "HEAD", ref)
    if base is None:
        raise WorkerError(f"cannot resolve merge base for {ref} "
                          "(make the ref available locally first)")
    ours_digest, ours_text = _read_handoff_text(ledger, cwd)
    base_digest, base_text = _read_handoff_text(ledger, cwd, ref=base)
    theirs_digest, theirs_text = _read_handoff_text(ledger, cwd, ref=ref)
    ours_id = parse_handoff_fields(ours_text)["handoff_id"] \
        if ours_text is not None else None
    base_id = parse_handoff_fields(base_text)["handoff_id"] \
        if base_text is not None else None
    theirs_id = parse_handoff_fields(theirs_text)["handoff_id"] \
        if theirs_text is not None else None
    norm = lambda value: value if value else "none"
    base_n, ours_n, theirs_n = norm(base_id), norm(ours_id), norm(theirs_id)
    if ours_n == theirs_n:
        classification = "unchanged" if ours_n == base_n else "successor"
    elif theirs_n == base_n:
        classification = "successor"
    elif ours_n == base_n:
        classification = "stale"
    else:
        classification = "sibling"
    required = sorted({value for value in (ours_n, theirs_n)
                       if value != "none"})
    _ = state_root  # local registry is not consulted by offline comparison
    if classification == "sibling":
        guidance = [
            "Make the other ref available locally first (fetch/pull); "
            "Statutor never touches the network.",
            "Resolve the substantive HANDOFF state by hand, then rewrite "
            "HANDOFF.md fresh with a new random handoff_id.",
            f"Name every id in supersedes: {', '.join(required)}.",
            "Attribute the rewrite (last_worker/last_machine), verify it, "
            "then record it with `statutor worker complete --session <id>` "
            "from a session started on the reconciled base.",
        ]
    elif classification == "stale":
        guidance = [
            f"Advance to {ref}: adopt its HANDOFF state, then rewrite with "
            "a fresh handoff_id superseding "
            f"{theirs_n} (and {base_n} when distinct).",
        ]
    elif classification == "successor":
        guidance = ["Current HANDOFF already supersedes the ref; no "
                    "reconciliation needed."]
    else:
        guidance = ["Both sides report the same handoff_id; no "
                    "reconciliation needed."]
    return {"schema_version": SCHEMA_VERSION, "scope": "portable-handoff",
            "operation": "worker-compare", "ref": ref, "merge_base": base,
            "base": {"digest": base_digest,
                     **_attribution_summary(base_text)},
            "ours": {"digest": ours_digest,
                     **_attribution_summary(ours_text)},
            "theirs": {"digest": theirs_digest,
                       **_attribution_summary(theirs_text)},
            "classification": classification,
            "reconciliation_must_supersede": required,
            "reconciliation_guidance": guidance,
            "note": "offline comparison only; Statutor never fetches, "
                    "merges, rewrites HANDOFF content, or selects a winner"}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _roots(args) -> substrate.ResolvedRoots:
    return substrate.resolve_roots(home=getattr(args, "home", None),
                                   config_root=getattr(args, "config_root",
                                                       None),
                                   state_root=getattr(args, "state_root",
                                                      None))


def _emit(data: object, json_output: bool) -> None:
    if json_output:
        print(json.dumps(data, sort_keys=True, indent=2))
    else:
        print(json.dumps(data, sort_keys=True))


def machine_cli(argv: list[str]) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="statutor machine")
    parser.add_argument("--home")
    parser.add_argument("--config-root")
    parser.add_argument("--state-root")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("show", "set-label", "rotate"):
        child = sub.add_parser(name)
        child.add_argument("--home")
        child.add_argument("--config-root")
        child.add_argument("--state-root")
        child.add_argument("--json", action="store_true")
        if name == "set-label":
            child.add_argument("label")
        if name == "rotate":
            child.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    roots = _roots(args)
    try:
        if args.command == "show":
            result = show_machine(Path(roots.state_root))
        elif args.command == "set-label":
            result = set_machine_label(Path(roots.state_root), args.label)
        else:
            if not args.confirm:
                print("rotation requires --confirm", file=sys.stderr)
                return 64
            preview = show_machine(Path(roots.state_root))
            print(json.dumps(preview, sort_keys=True, indent=2),
                  file=sys.stderr)
            result = rotate_machine(Path(roots.state_root), confirm=True)
    except (WorkerError, substrate.GlobalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _emit(result, args.json)
    return 0


def worker_cli(argv: list[str]) -> int:
    # CLI-to-plan traceability (plans/v0.5-worker-provenance.md): the contract
    # block names each command; `[metadata]` on `record` covers --role,
    # --origin-harness, and --session (vocabulary + session baselines live in
    # the Vocabulary/Local-registry sections); `complete --session` and
    # `compare REF` match the contract verbatim; `capabilities` reports the
    # schema's capability metadata (T-0041 "capability reporting"); `new-id`
    # mints the fresh random ids the portable-completion section requires;
    # --cwd/--home/--config-root/--state-root are hermetic-test plumbing,
    # same pattern as the global CLI. `machine rotate --confirm` is the
    # plan's "explicit confirmation" before rotation.
    import argparse
    parser = argparse.ArgumentParser(prog="statutor worker")
    parser.add_argument("--home")
    parser.add_argument("--config-root")
    parser.add_argument("--state-root")
    sub = parser.add_subparsers(dest="command", required=True)
    begin = sub.add_parser("begin")
    begin.add_argument("--home")
    begin.add_argument("--config-root")
    begin.add_argument("--state-root")
    begin.add_argument("--harness", required=True, choices=HARNESSES)
    begin.add_argument("--role", default="unknown", choices=ROLES)
    begin.add_argument("--origin-harness", default="unknown",
                       choices=HARNESSES)
    begin.add_argument("--session")
    begin.add_argument("--cwd")
    begin.add_argument("--json", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("--home")
    show.add_argument("--config-root")
    show.add_argument("--state-root")
    show.add_argument("--basis", default="completed", choices=BASES)
    show.add_argument("--worktree", action="store_true")
    show.add_argument("--cwd")
    show.add_argument("--json", action="store_true")
    active = sub.add_parser("active")
    active.add_argument("--home")
    active.add_argument("--config-root")
    active.add_argument("--state-root")
    active.add_argument("--worktree", action="store_true")
    active.add_argument("--cwd")
    active.add_argument("--json", action="store_true")
    record = sub.add_parser("record")
    record.add_argument("--home")
    record.add_argument("--config-root")
    record.add_argument("--state-root")
    record.add_argument("--harness", required=True, choices=HARNESSES)
    record.add_argument("--event", required=True, choices=EVENTS)
    record.add_argument("--role", default="unknown", choices=ROLES)
    record.add_argument("--origin-harness", default="unknown",
                        choices=HARNESSES)
    record.add_argument("--session")
    record.add_argument("--cwd")
    record.add_argument("--json", action="store_true")
    complete = sub.add_parser("complete")
    complete.add_argument("--home")
    complete.add_argument("--config-root")
    complete.add_argument("--state-root")
    complete.add_argument("--session", required=True)
    complete.add_argument("--cwd")
    complete.add_argument("--json", action="store_true")
    compare = sub.add_parser("compare")
    compare.add_argument("--home")
    compare.add_argument("--config-root")
    compare.add_argument("--state-root")
    compare.add_argument("ref")
    compare.add_argument("--cwd")
    compare.add_argument("--json", action="store_true")
    capabilities = sub.add_parser("capabilities")
    capabilities.add_argument("--home")
    capabilities.add_argument("--config-root")
    capabilities.add_argument("--state-root")
    capabilities.add_argument("--json", action="store_true")
    new_id = sub.add_parser(
        "new-id",
        help="mint a fresh random handoff id for a HANDOFF rewrite")
    new_id.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    roots = _roots(args)
    cwd = getattr(args, "cwd", None) or os.getcwd()
    try:
        if args.command == "begin":
            result = worker_begin(Path(roots.state_root), cwd,
                                  harness=args.harness, role=args.role,
                                  origin_harness=args.origin_harness,
                                  session_id=args.session)
        elif args.command == "show":
            result = worker_show(Path(roots.state_root), cwd,
                                 basis=args.basis,
                                 worktree_only=args.worktree)
        elif args.command == "active":
            result = worker_active(Path(roots.state_root), cwd,
                                   worktree_only=args.worktree)
        elif args.command == "record":
            result = worker_record(Path(roots.state_root), cwd,
                                   harness=args.harness, event=args.event,
                                   role=args.role,
                                   origin_harness=args.origin_harness,
                                   session_id=args.session)
        elif args.command == "complete":
            result = worker_complete(Path(roots.state_root), cwd,
                                     session_id=args.session)
        elif args.command == "compare":
            result = worker_compare(Path(roots.state_root), cwd, ref=args.ref)
        elif args.command == "capabilities":
            result = all_capabilities()
        else:
            token = secrets.token_hex(16)
            if getattr(args, "json", False):
                result = {"schema_version": SCHEMA_VERSION,
                          "handoff_id": token}
            else:
                print(token)
                return 0
    except (WorkerError, substrate.GlobalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _emit(result, getattr(args, "json", False))
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "machine":
        raise SystemExit(machine_cli(sys.argv[2:]))
    raise SystemExit(worker_cli(sys.argv[2:]))
