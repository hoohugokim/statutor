#!/usr/bin/env python3
"""Safety substrate for Statutor's opt-in portable user layer (D-0018).

This module has no third-party dependencies. It resolves host roots, validates
versioned JSON, hashes safe filesystem trees, serializes operations, performs
compare-and-swap writes, and creates/restores exact backups. Higher-level
instruction and skill policy lives above these primitives.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterator, Mapping


SCHEMA_VERSION = 1
HOSTS = ("claude", "codex", "opencode")
JOURNAL_STATUSES = {
    "planned", "applying", "complete", "failed", "rolling_back",
    "rolled_back",
}
ABSENT = "absent"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")


class GlobalError(RuntimeError):
    """Base error for deterministic global-layer failures."""


class SchemaError(GlobalError):
    """A versioned JSON document is invalid or unsupported."""


class UnsafeTree(GlobalError):
    """A tree contains an unsafe file type or link topology."""


class ConcurrentChange(GlobalError):
    """A compare-and-swap precondition no longer matches."""


class LockBusy(GlobalError):
    """Another Statutor global operation owns the state lock."""


@dataclass(frozen=True)
class ResolvedRoots:
    home: str
    config_root: str
    state_root: str
    claude_home: str
    codex_home: str
    opencode_home: str
    portable_skills: str

    def to_json(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class Fingerprint:
    kind: str
    digest: str | None
    mode: int | None = None

    @property
    def token(self) -> str:
        if self.kind == ABSENT:
            return ABSENT
        mode = "" if self.mode is None else f":{self.mode:04o}"
        return f"{self.kind}:{self.digest}{mode}"

    def to_json(self) -> dict[str, object]:
        return {"kind": self.kind, "digest": self.digest, "mode": self.mode}


def _absolute(path: str | os.PathLike[str]) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return Path(os.path.abspath(candidate))


def resolve_roots(
    *,
    home: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
    state_root: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> ResolvedRoots:
    """Resolve logical roots without mutating HOME or following root symlinks."""
    env = dict(os.environ if environ is None else environ)
    os_name = os.name if platform is None else platform
    raw_home = home or env.get("HOME") or env.get("USERPROFILE")
    if raw_home is None:
        raw_home = str(Path.home())
    user_home = _absolute(raw_home)

    if os_name == "nt":
        config_base = _absolute(
            env.get("APPDATA", user_home / "AppData" / "Roaming"))
        state_base = _absolute(
            env.get("LOCALAPPDATA", user_home / "AppData" / "Local"))
        default_config = config_base / "statutor"
        default_state = state_base / "statutor" / "state"
    else:
        config_base = _absolute(env.get("XDG_CONFIG_HOME", user_home / ".config"))
        state_base = _absolute(
            env.get("XDG_STATE_HOME", user_home / ".local" / "state"))
        default_config = config_base / "statutor"
        default_state = state_base / "statutor"

    resolved_config = _absolute(config_root or default_config)
    resolved_state = _absolute(state_root or default_state)
    claude_home = _absolute(
        env.get("CLAUDE_CONFIG_DIR", user_home / ".claude"))
    codex_home = _absolute(env.get("CODEX_HOME", user_home / ".codex"))
    opencode_home = config_base / "opencode"

    return ResolvedRoots(
        home=str(user_home),
        config_root=str(resolved_config),
        state_root=str(resolved_state),
        claude_home=str(claude_home),
        codex_home=str(codex_home),
        opencode_home=str(opencode_home),
        portable_skills=str(user_home / ".agents" / "skills"),
    )


def default_config() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "hosts": list(HOSTS),
        "instructions": {
            "common": "AGENTS.md",
            "overlays": {host: f"hosts/{host}.md" for host in HOSTS},
        },
        "skills": {
            "source": "skills",
            "targets": ["portable", "claude"],
        },
    }


def default_state() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generation": 0,
        "artifacts": {},
        "backups": {},
    }


def _relative_config_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SchemaError(f"{field} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise SchemaError(f"{field} must stay inside the config root")
    return value


def _exact_keys(data: dict, expected: set[str], label: str) -> None:
    keys = set(data)
    if keys != expected:
        raise SchemaError(
            f"{label} keys differ: missing={sorted(expected - keys)}, "
            f"unknown={sorted(keys - expected)}")


def validate_config(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise SchemaError("global config must be a JSON object")
    _exact_keys(
        data, {"schema_version", "hosts", "instructions", "skills"},
        "global config",
    )
    if data["schema_version"] != SCHEMA_VERSION:
        raise SchemaError(
            f"unsupported global config schema {data['schema_version']!r}")
    hosts = data["hosts"]
    if not isinstance(hosts, list) or not hosts or any(
        not isinstance(host, str) or host not in HOSTS for host in hosts
    ) or len(hosts) != len(set(hosts)):
        raise SchemaError("hosts must be a unique non-empty supported-host list")

    instructions = data["instructions"]
    if not isinstance(instructions, dict):
        raise SchemaError("instructions must be an object")
    _exact_keys(instructions, {"common", "overlays"}, "instructions")
    _relative_config_path(instructions["common"], "instructions.common")
    overlays = instructions["overlays"]
    if not isinstance(overlays, dict) or set(overlays) != set(HOSTS):
        raise SchemaError("instructions.overlays must name every supported host")
    for host, value in overlays.items():
        _relative_config_path(value, f"instructions.overlays.{host}")

    skills = data["skills"]
    if not isinstance(skills, dict):
        raise SchemaError("skills must be an object")
    _exact_keys(skills, {"source", "targets"}, "skills")
    _relative_config_path(skills["source"], "skills.source")
    targets = skills["targets"]
    if targets != ["portable", "claude"]:
        raise SchemaError(
            "skills.targets must be ['portable', 'claude'] in schema 1")
    return data


def validate_state(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise SchemaError("global state must be a JSON object")
    _exact_keys(
        data, {"schema_version", "generation", "artifacts", "backups"},
        "global state",
    )
    if data["schema_version"] != SCHEMA_VERSION:
        raise SchemaError(
            f"unsupported global state schema {data['schema_version']!r}")
    if not isinstance(data["generation"], int) or data["generation"] < 0:
        raise SchemaError("global state generation must be a non-negative integer")
    if not isinstance(data["artifacts"], dict):
        raise SchemaError("global state artifacts must be an object")
    for artifact_id, receipt in data["artifacts"].items():
        if not isinstance(artifact_id, str) or not re.fullmatch(
            r"[a-zA-Z0-9._-]{1,128}", artifact_id
        ):
            raise SchemaError("global state has an invalid artifact id")
        validate_artifact_receipt(receipt)
    if not isinstance(data["backups"], dict):
        raise SchemaError("global state backups must be an object")
    for backup_id, manifest in data["backups"].items():
        if not isinstance(backup_id, str) or not re.fullmatch(
            r"[a-zA-Z0-9._-]{1,128}", backup_id
        ):
            raise SchemaError("global state has an invalid backup id")
        _relative_config_path(manifest, f"backups.{backup_id}")
    return data


def validate_artifact_receipt(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise SchemaError("artifact receipt must be an object")
    expected = {
        "kind", "name", "target_scope", "source_logical", "source_real",
        "target_logical", "target_real", "source_digest", "installed_token",
        "backup_id", "ownership",
    }
    _exact_keys(data, expected, "artifact receipt")
    if data["kind"] not in {"instruction", "skill"}:
        raise SchemaError("artifact receipt kind must be instruction or skill")
    if not isinstance(data["name"], str) or not re.fullmatch(
        r"[a-zA-Z0-9._-]{1,128}", data["name"]
    ):
        raise SchemaError("artifact receipt name is invalid")
    scopes = set(HOSTS) | {"portable"}
    if data["target_scope"] not in scopes:
        raise SchemaError("artifact receipt target_scope is unsupported")
    for field in (
        "source_logical", "source_real", "target_logical", "target_real",
    ):
        value = data[field]
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise SchemaError(f"artifact receipt {field} must be absolute")
    if not isinstance(data["source_digest"], str) or not _SHA256_RE.fullmatch(
        data["source_digest"]
    ):
        raise SchemaError("artifact receipt source_digest is invalid")
    token = data["installed_token"]
    if not isinstance(token, str) or token == ABSENT or not re.fullmatch(
        r"(?:file|tree|symlink):sha256:[0-9a-f]{64}(?::[0-7]{4})?", token
    ):
        raise SchemaError("artifact receipt installed_token is invalid")
    backup_id = data["backup_id"]
    if backup_id is not None and (
        not isinstance(backup_id, str)
        or not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", backup_id)
    ):
        raise SchemaError("artifact receipt backup_id is invalid")
    if data["ownership"] != "statutor":
        raise SchemaError("artifact receipt ownership must be statutor")
    return data


def canonical_json(data: object) -> bytes:
    return (
        json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaError(f"cannot read JSON {path}: {exc}") from exc


def content_digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_link_graph(root: Path, root_real: Path) -> None:
    """Follow directory-link edges only to detect escaping, broken, or cycles."""
    def visit(directory: Path, stack: tuple[tuple[int, int], ...]) -> None:
        try:
            directory_stat = directory.stat()
        except (OSError, RuntimeError) as exc:
            raise UnsafeTree(f"cannot resolve directory {directory}: {exc}") from exc
        identity = (directory_stat.st_dev, directory_stat.st_ino)
        if identity in stack:
            raise UnsafeTree(f"cyclic directory link at {directory}")
        next_stack = stack + (identity,)
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise UnsafeTree(f"cannot scan {directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                entry_stat = path.lstat()
            except OSError as exc:
                raise UnsafeTree(f"cannot inspect {path}: {exc}") from exc
            if stat.S_ISLNK(entry_stat.st_mode):
                try:
                    target = path.resolve(strict=True)
                except (OSError, RuntimeError) as exc:
                    raise UnsafeTree(f"broken or cyclic link {path}: {exc}") from exc
                if not _within(target, root_real):
                    raise UnsafeTree(f"link escapes tree: {path} -> {os.readlink(path)}")
                if target.is_dir():
                    visit(path, next_stack)
            elif stat.S_ISDIR(entry_stat.st_mode):
                visit(path, next_stack)
            elif not stat.S_ISREG(entry_stat.st_mode):
                raise UnsafeTree(f"special file is not allowed: {path}")

    visit(root, ())


def _tree_entries(root: Path) -> list[tuple[str, str, int, bytes]]:
    if not root.is_dir():
        raise UnsafeTree(f"tree root is not a directory: {root}")
    try:
        root_real = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise UnsafeTree(f"cannot resolve tree root {root}: {exc}") from exc
    _validate_link_graph(root, root_real)
    entries: list[tuple[str, str, int, bytes]] = []

    def walk(directory: Path) -> None:
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise UnsafeTree(f"cannot scan {directory}: {exc}") from exc
        for child in children:
            path = Path(child.path)
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISDIR(info.st_mode):
                entries.append((relative, "directory", mode, b""))
                walk(path)
            elif stat.S_ISREG(info.st_mode):
                entries.append((relative, "file", mode, path.read_bytes()))
            elif stat.S_ISLNK(info.st_mode):
                entries.append((
                    relative, "symlink", mode,
                    os.readlink(path).encode("utf-8", "surrogateescape"),
                ))
            else:
                raise UnsafeTree(f"special file is not allowed: {path}")

    walk(root)
    return entries


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, kind, mode, content in _tree_entries(root):
        for field in (
            kind.encode("ascii"),
            relative.encode("utf-8", "surrogateescape"),
            f"{mode:04o}".encode("ascii"),
            content,
        ):
            digest.update(len(field).to_bytes(8, "big"))
            digest.update(field)
    return "sha256:" + digest.hexdigest()


def fingerprint(path: Path) -> Fingerprint:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return Fingerprint(ABSENT, None, None)
    except OSError as exc:
        raise GlobalError(f"cannot inspect {path}: {exc}") from exc
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISREG(info.st_mode):
        return Fingerprint("file", content_digest(path.read_bytes()), mode)
    if stat.S_ISDIR(info.st_mode):
        return Fingerprint("tree", tree_digest(path), mode)
    if stat.S_ISLNK(info.st_mode):
        target = os.readlink(path).encode("utf-8", "surrogateescape")
        return Fingerprint("symlink", content_digest(target), mode)
    raise UnsafeTree(f"special target is not allowed: {path}")


def _require_expected(path: Path, expected: str) -> Fingerprint:
    current = fingerprint(path)
    if current.token != expected:
        raise ConcurrentChange(
            f"{path} changed: expected {expected}, found {current.token}")
    return current


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(
    target: Path,
    content: bytes,
    *,
    expected: str,
    mode: int = 0o600,
) -> Fingerprint:
    """Atomically replace a regular file if its fingerprint still matches."""
    target = _absolute(target)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = _require_expected(target, expected)
    if current.kind not in (ABSENT, "file"):
        raise GlobalError(f"refusing to replace non-file target: {target}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.statutor-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        _require_expected(target, expected)
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
    return fingerprint(target)


def atomic_write_json(
    target: Path,
    data: object,
    *,
    expected: str,
    mode: int = 0o600,
) -> Fingerprint:
    return atomic_write_bytes(
        target, canonical_json(data), expected=expected, mode=mode)


def _copy_safe_tree(source: Path, destination: Path) -> None:
    entries = _tree_entries(source)
    root_mode = stat.S_IMODE(source.lstat().st_mode)
    destination.mkdir(mode=root_mode)
    os.chmod(destination, root_mode)
    directories = [destination]
    for relative, kind, mode, content in entries:
        target = destination / relative
        if kind == "directory":
            target.mkdir(mode=mode)
            os.chmod(target, mode)
            directories.append(target)
        elif kind == "file":
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(target, mode)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(content.decode("utf-8", "surrogateescape"), target)
    for directory in reversed(directories):
        _fsync_directory(directory)


def _remove_artifact(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def atomic_replace_tree(
    target: Path,
    source: Path,
    *,
    expected: str,
) -> Fingerprint:
    """Install a validated tree with CAS and a same-parent rollback rename."""
    target = _absolute(target)
    source = _absolute(source)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = _require_expected(target, expected)
    if current.kind not in (ABSENT, "tree"):
        raise GlobalError(f"refusing to replace non-directory target: {target}")

    temporary = Path(tempfile.mkdtemp(
        prefix=f".{target.name}.statutor-new-", dir=target.parent))
    temporary.rmdir()
    old = target.parent / f".{target.name}.statutor-old-{secrets.token_hex(8)}"
    moved_old = False
    try:
        _copy_safe_tree(source, temporary)
        _require_expected(target, expected)
        if current.kind == "tree":
            os.replace(target, old)
            moved_old = True
        try:
            os.replace(temporary, target)
        except BaseException:
            if moved_old and not target.exists() and old.exists():
                os.replace(old, target)
                moved_old = False
            raise
        _fsync_directory(target.parent)
        if moved_old:
            shutil.rmtree(old)
            moved_old = False
    finally:
        _remove_artifact(temporary)
        if moved_old:
            _remove_artifact(old)
    return fingerprint(target)


class StateLock:
    """A conservative mkdir lock; stale locks require explicit recovery."""

    def __init__(self, state_root: Path):
        self.state_root = _absolute(state_root)
        self.path = self.state_root / ".global.lock"
        self.acquired = False

    def __enter__(self) -> "StateLock":
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.path.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise LockBusy(f"global state lock is busy: {self.path}") from exc
        self.acquired = True
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "pid": os.getpid(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (self.path / "owner.json").write_bytes(canonical_json(metadata))
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.acquired:
            with contextlib.suppress(FileNotFoundError):
                (self.path / "owner.json").unlink()
            with contextlib.suppress(FileNotFoundError):
                self.path.rmdir()
            self.acquired = False


def create_journal(
    state_root: Path,
    *,
    action: str,
    plan_digest: str,
    operation_id: str | None = None,
) -> tuple[Path, dict[str, object]]:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", action):
        raise SchemaError("journal action must be a lowercase hyphenated name")
    identifier = operation_id or secrets.token_hex(16)
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", identifier):
        raise SchemaError("invalid operation id")
    journal = {
        "schema_version": SCHEMA_VERSION,
        "operation_id": identifier,
        "action": action,
        "status": "planned",
        "plan_digest": plan_digest,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
        "error": None,
    }
    directory = _absolute(state_root) / "journals"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{identifier}.json"
    atomic_write_json(path, journal, expected=ABSENT)
    return path, journal


def update_journal(
    path: Path,
    journal: dict[str, object],
    *,
    status: str,
    step: dict[str, object] | None = None,
    error: str | None = None,
) -> tuple[dict[str, object], Fingerprint]:
    if status not in JOURNAL_STATUSES:
        raise SchemaError(f"invalid journal status: {status}")
    before = fingerprint(path).token
    updated = dict(journal)
    updated["status"] = status
    updated["error"] = error
    steps = list(updated.get("steps", []))
    if step is not None:
        steps.append(step)
    updated["steps"] = steps
    result = atomic_write_json(path, updated, expected=before)
    return updated, result


def create_backup(
    state_root: Path,
    target: Path,
    *,
    operation_id: str,
    artifact_id: str,
) -> tuple[Path, dict[str, object]]:
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", artifact_id):
        raise SchemaError("invalid backup artifact id")
    target = _absolute(target)
    backup_dir = _absolute(state_root) / "backups" / operation_id / artifact_id
    if backup_dir.exists():
        raise GlobalError(f"backup already exists: {backup_dir}")
    backup_dir.mkdir(parents=True, mode=0o700)
    original = fingerprint(target)
    payload = backup_dir / "payload"
    if original.kind == "file":
        with open(payload, "wb") as handle:
            handle.write(target.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(payload, original.mode or 0o600)
    elif original.kind == "tree":
        _copy_safe_tree(target, payload)
    elif original.kind == "symlink":
        os.symlink(os.readlink(target), payload)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "operation_id": operation_id,
        "artifact_id": artifact_id,
        "logical_target": str(target),
        "real_parent": str(target.parent.resolve(strict=False)),
        "original": original.to_json(),
        "original_token": original.token,
        "payload": None if original.kind == ABSENT else "payload",
    }
    manifest_path = backup_dir / "manifest.json"
    atomic_write_json(manifest_path, manifest, expected=ABSENT)
    return manifest_path, manifest


def restore_backup(
    manifest_path: Path,
    target: Path,
    *,
    expected_current: str,
) -> Fingerprint:
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise SchemaError("invalid backup manifest")
    target = _absolute(target)
    if manifest.get("logical_target") != str(target):
        raise SchemaError("backup target does not match the requested target")
    _require_expected(target, expected_current)
    original = manifest.get("original")
    if not isinstance(original, dict) or original.get("kind") not in {
        ABSENT, "file", "tree", "symlink",
    }:
        raise SchemaError("backup manifest has invalid original fingerprint")
    kind = original["kind"]
    payload = manifest_path.parent / "payload"
    if kind == ABSENT:
        _remove_artifact(target)
        _fsync_directory(target.parent)
        return fingerprint(target)
    if kind == "file":
        return atomic_write_bytes(
            target,
            payload.read_bytes(),
            expected=expected_current,
            mode=int(original.get("mode") or 0o600),
        )
    if kind == "tree":
        return atomic_replace_tree(target, payload, expected=expected_current)
    _remove_artifact(target)
    os.symlink(os.readlink(payload), target)
    _fsync_directory(target.parent)
    return fingerprint(target)
