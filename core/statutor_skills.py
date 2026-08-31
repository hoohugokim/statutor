#!/usr/bin/env python3
"""Portable Agent Skill lifecycle for Statutor's D-0018 user layer."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
from pathlib import Path

import statutor_global as substrate
import statutor_global_cli as instructions


SKILL_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _frontmatter_scalar(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise substrate.SchemaError("invalid quoted skill frontmatter") from exc
        if not isinstance(parsed, str):
            raise substrate.SchemaError("skill frontmatter scalar must be text")
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise substrate.SchemaError("invalid quoted skill frontmatter")
        return value[1:-1].replace("''", "'")
    return value


def skill_metadata(skill_root: Path) -> dict[str, str]:
    """Read required Agent Skills metadata without normalizing extensions."""
    if skill_root.is_symlink() or not skill_root.is_dir():
        raise substrate.UnsafeTree("skill root must be a real directory")
    entrypoint = skill_root / "SKILL.md"
    try:
        text = entrypoint.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise substrate.SchemaError(f"cannot read {entrypoint}: {exc}") from exc
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise substrate.SchemaError("SKILL.md must begin with YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise substrate.SchemaError("SKILL.md frontmatter is not closed") from exc
    metadata: dict[str, str] = {}
    index = 1
    while index < end:
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line[:1].isspace() or ":" not in line:
            index += 1
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        if key in metadata:
            raise substrate.SchemaError(f"duplicate skill frontmatter field: {key}")
        raw = raw.strip()
        if raw in {"|", "|-", "|+", ">", ">-", ">+"}:
            block: list[str] = []
            index += 1
            while index < end and (not lines[index] or lines[index][:1].isspace()):
                block.append(lines[index].lstrip())
                index += 1
            separator = "\n" if raw.startswith("|") else " "
            metadata[key] = separator.join(block).strip()
            continue
        metadata[key] = _frontmatter_scalar(raw)
        index += 1
    name = metadata.get("name", "")
    description = metadata.get("description", "")
    if not SKILL_NAME_RE.fullmatch(name) or len(name) > 64:
        raise substrate.SchemaError("skill name violates the Agent Skills specification")
    if name != skill_root.name:
        raise substrate.SchemaError("skill name must match its parent directory")
    if not 1 <= len(description) <= 1024:
        raise substrate.SchemaError("skill description must contain 1-1024 characters")
    substrate.tree_digest(skill_root)
    return {"name": name, "description": description}


def _context(roots: substrate.ResolvedRoots):
    config = instructions._load_config(roots)
    state = instructions._load_state(roots)
    skills = config["skills"]
    assert isinstance(skills, dict)
    return config, state, Path(roots.config_root) / str(skills["source"])


def foreign_locked_names(roots: substrate.ResolvedRoots) -> set[str]:
    lock = Path(roots.home) / ".agents" / ".skill-lock.json"
    if not lock.exists():
        return set()
    data = substrate.load_json(lock)
    if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
        raise substrate.SchemaError("foreign skill lock has unsupported schema")
    return {name for name in data["skills"] if isinstance(name, str)}


def skill_import_plan(
    roots: substrate.ResolvedRoots, source: Path,
) -> dict[str, object]:
    source = Path(os.path.abspath(source.expanduser()))
    if not source.is_dir():
        raise substrate.GlobalError("skill import requires a local directory")
    metadata = skill_metadata(source)
    _, _, canonical_root = _context(roots)
    target = canonical_root / metadata["name"]
    current = substrate.fingerprint(target)
    action = "import" if current.kind == substrate.ABSENT else "conflict"
    reason = None if action == "import" else "canonical skill source already exists"
    plan = {
        "schema_version": substrate.SCHEMA_VERSION,
        "operation": "skill-import",
        "roots": roots.to_json(),
        "items": [{
            "name": metadata["name"],
            "source": str(source),
            "source_digest": substrate.tree_digest(source),
            "target": str(target),
            "current_token": current.token,
            "action": action,
            "reason": reason,
        }],
    }
    plan["plan_digest"] = substrate.content_digest(substrate.canonical_json(plan))
    return plan


def import_skill(roots: substrate.ResolvedRoots, source: Path) -> dict[str, object]:
    state_root = Path(roots.state_root)
    with substrate.StateLock(state_root):
        plan = skill_import_plan(roots, source)
        item = plan["items"][0]
        assert isinstance(item, dict)
        if item["action"] == "conflict":
            raise substrate.GlobalError(str(item["reason"]))
        source = Path(str(item["source"]))
        target = Path(str(item["target"]))
        operation_id = os.urandom(16).hex()
        journal_path, journal = substrate.create_journal(
            state_root, action="skill-import",
            plan_digest=str(plan["plan_digest"]), operation_id=operation_id)
        journal, _ = substrate.update_journal(
            journal_path, journal, status="applying")
        rollback_manifest, _ = substrate.create_backup(
            state_root, target, operation_id=operation_id,
            artifact_id=f"import-{item['name']}")
        result: substrate.Fingerprint | None = None
        try:
            result = substrate.atomic_replace_tree(
                target, source, expected=str(item["current_token"]))
            journal, _ = substrate.update_journal(
                journal_path, journal, status="applying",
                step={"name": item["name"], "status": "imported"})
            substrate.update_journal(journal_path, journal, status="complete")
        except BaseException as error:
            if result is not None:
                with contextlib.suppress(Exception):
                    substrate.restore_backup(
                        rollback_manifest, target, expected_current=result.token)
            with contextlib.suppress(substrate.GlobalError):
                substrate.update_journal(
                    journal_path, journal, status="failed", error=str(error))
            raise
    return {
        "schema_version": 1,
        "name": str(item["name"]),
        "source": str(source),
        "canonical": str(target),
        "plan_digest": str(plan["plan_digest"]),
        "digest": result.digest,
    }


def _canonical_skills(root: Path) -> list[tuple[str, Path, str, str | None]]:
    if not root.exists():
        return []
    if not root.is_dir():
        raise substrate.GlobalError("canonical skills root is not a directory")
    found = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if not path.is_dir():
            raise substrate.UnsafeTree(f"unexpected canonical skill entry: {path}")
        try:
            metadata = skill_metadata(path)
            found.append((metadata["name"], path, substrate.tree_digest(path), None))
        except substrate.GlobalError as error:
            found.append((path.name, path, "", str(error)))
    return found


def _skill_targets(roots: substrate.ResolvedRoots, name: str) -> list[tuple[str, Path]]:
    return [
        ("portable", Path(roots.portable_skills) / name),
        ("claude", Path(roots.claude_home) / "skills" / name),
    ]


def skill_plan(
    roots: substrate.ResolvedRoots,
    *,
    adopt_identical: bool = False,
) -> dict[str, object]:
    _, state, canonical_root = _context(roots)
    artifacts = state["artifacts"]
    assert isinstance(artifacts, dict)
    locked = foreign_locked_names(roots)
    items = []
    duplicates = []
    for name, source, digest, invalid in _canonical_skills(canonical_root):
        target_digests = []
        for scope, target in _skill_targets(roots, name):
            current = substrate.fingerprint(target)
            receipt = artifacts.get(f"skill-{name}-{scope}")
            reason = None
            if invalid:
                action, reason = "conflict", f"invalid canonical skill: {invalid}"
            elif name in locked:
                action, reason = "foreign-managed", "name is present in foreign lock"
            elif receipt is None:
                if current.kind == substrate.ABSENT:
                    action = "create"
                elif current.kind == "tree" and current.digest == digest:
                    action = "adopt-identical" if adopt_identical else "conflict"
                    reason = None if adopt_identical else "identical unmanaged target; use --adopt-identical"
                else:
                    action, reason = "conflict", "differing unmanaged target"
            elif current.token != receipt["installed_token"]:
                action, reason = "conflict", "managed target is missing or modified"
            elif current.digest == digest:
                action = "noop"
            else:
                action = "update"
            if current.kind == "tree":
                target_digests.append(current.digest)
            items.append({
                "name": name, "scope": scope, "source": str(source),
                "source_digest": digest, "target": str(target),
                "current_token": current.token, "action": action, "reason": reason,
            })
        if len(target_digests) == 2:
            classification = "identical" if len(set(target_digests)) == 1 else "divergent"
        elif target_digests:
            classification = "single"
        else:
            classification = "missing"
        duplicates.append({"name": name, "classification": classification})
    plan = {
        "schema_version": 1,
        "operation": "skill-apply",
        "roots": roots.to_json(),
        "foreign_locked": sorted(locked),
        "items": items,
        "duplicates": duplicates,
    }
    plan["plan_digest"] = substrate.content_digest(substrate.canonical_json(plan))
    return plan


def skill_status(roots: substrate.ResolvedRoots) -> dict[str, object]:
    plan = skill_plan(roots)
    statuses = {
        "create": "missing", "noop": "installed", "update": "outdated",
        "conflict": "conflict", "foreign-managed": "foreign-managed",
    }
    plan["items"] = [
        {**item, "status": statuses[str(item["action"])]}
        for item in plan["items"]
    ]
    plan["operation"] = "skill-status"
    return plan


def _skill_receipt(
    name: str, scope: str, source: Path, target: Path,
    source_digest: str, token: str, backup_id: str,
) -> dict[str, object]:
    return {
        "kind": "skill", "name": name, "target_scope": scope,
        "source_logical": str(source.absolute()),
        "source_real": str(source.resolve(strict=True)),
        "target_logical": str(target.absolute()),
        "target_real": str(target.resolve(strict=True)),
        "source_digest": source_digest, "installed_token": token,
        "backup_id": backup_id, "ownership": "statutor",
    }


def apply_skills(
    roots: substrate.ResolvedRoots, *, adopt_identical: bool = False,
) -> dict[str, object]:
    state_root = Path(roots.state_root)
    with substrate.StateLock(state_root):
        plan = skill_plan(roots, adopt_identical=adopt_identical)
        conflicts = [item for item in plan["items"] if item["action"] == "conflict"]
        if conflicts:
            raise substrate.GlobalError("skill plan has conflicts; nothing changed")
        changes = [
            item for item in plan["items"]
            if item["action"] in {"create", "update", "adopt-identical"}
        ]
        if not changes:
            return plan
        state = instructions._load_state(roots)
        state_path = instructions._state_path(roots)
        state_expected = substrate.fingerprint(state_path).token
        artifacts = dict(state["artifacts"])
        backups = dict(state["backups"])
        operation_id = os.urandom(16).hex()
        journal_path, journal = substrate.create_journal(
            state_root, action="skill-apply",
            plan_digest=str(plan["plan_digest"]), operation_id=operation_id)
        journal, _ = substrate.update_journal(journal_path, journal, status="applying")
        installed: list[tuple[Path, Path, str]] = []
        committed = False
        try:
            for item in changes:
                name, scope = str(item["name"]), str(item["scope"])
                source, target = Path(str(item["source"])), Path(str(item["target"]))
                backup_key = f"{operation_id}.{name}.{scope}"
                manifest, _ = substrate.create_backup(
                    state_root, target, operation_id=operation_id,
                    artifact_id=f"{name}-{scope}")
                previous = artifacts.get(f"skill-{name}-{scope}")
                if item["action"] == "adopt-identical":
                    result = substrate.fingerprint(target)
                else:
                    result = substrate.atomic_replace_tree(
                        target, source, expected=str(item["current_token"]))
                    installed.append((target, manifest, result.token))
                initial_backup = (
                    str(previous["backup_id"]) if isinstance(previous, dict)
                    else backup_key)
                artifacts[f"skill-{name}-{scope}"] = _skill_receipt(
                    name, scope, source, target, str(item["source_digest"]),
                    result.token, initial_backup)
                backups[backup_key] = str(manifest.relative_to(state_root))
                journal, _ = substrate.update_journal(
                    journal_path, journal, status="applying",
                    step={"name": name, "scope": scope, "status": "installed"})
            updated = {
                **state, "generation": int(state["generation"]) + 1,
                "artifacts": artifacts, "backups": backups,
            }
            substrate.validate_state(updated)
            substrate.atomic_write_json(state_path, updated, expected=state_expected)
            committed = True
            substrate.update_journal(journal_path, journal, status="complete")
        except BaseException as error:
            if not committed:
                for target, manifest, token in reversed(installed):
                    with contextlib.suppress(Exception):
                        substrate.restore_backup(manifest, target, expected_current=token)
            with contextlib.suppress(substrate.GlobalError):
                substrate.update_journal(
                    journal_path, journal, status="failed", error=str(error))
            raise
    return skill_plan(roots)


def skill_uninstall_plan(roots: substrate.ResolvedRoots) -> dict[str, object]:
    state = instructions._load_state(roots)
    artifacts = state["artifacts"]
    backups = state["backups"]
    assert isinstance(artifacts, dict) and isinstance(backups, dict)
    locked = foreign_locked_names(roots)
    items = []
    for key, receipt in sorted(artifacts.items()):
        if not key.startswith("skill-"):
            continue
        assert isinstance(receipt, dict)
        target = Path(str(receipt["target_logical"]))
        current = substrate.fingerprint(target)
        if str(receipt["name"]) in locked:
            action, reason = "conflict", "name is present in foreign lock"
        elif current.token != receipt["installed_token"]:
            action, reason = "conflict", "managed target is missing or modified"
        elif str(receipt["backup_id"]) not in backups:
            action, reason = "conflict", "initial backup is missing"
        else:
            action, reason = "restore", None
        items.append({
            "artifact": key,
            "name": receipt["name"],
            "scope": receipt["target_scope"],
            "target": str(target),
            "current_token": current.token,
            "action": action,
            "reason": reason,
        })
    plan = {
        "schema_version": substrate.SCHEMA_VERSION,
        "operation": "skill-uninstall",
        "roots": roots.to_json(),
        "items": items,
    }
    plan["plan_digest"] = substrate.content_digest(substrate.canonical_json(plan))
    return plan


def uninstall_skills(roots: substrate.ResolvedRoots) -> dict[str, object]:
    state_root = Path(roots.state_root)
    with substrate.StateLock(state_root):
        plan = skill_uninstall_plan(roots)
        conflicts = [
            item for item in plan["items"] if item["action"] == "conflict"
        ]
        if conflicts:
            raise substrate.GlobalError(
                "skill uninstall plan has modified or incomplete targets; "
                "nothing changed")
        state = instructions._load_state(roots)
        artifacts = dict(state["artifacts"])
        backups = state["backups"]
        assert isinstance(backups, dict)
        state_path = instructions._state_path(roots)
        state_expected = substrate.fingerprint(state_path).token
        candidates = []
        for item in plan["items"]:
            key = str(item["artifact"])
            receipt = artifacts[key]
            assert isinstance(receipt, dict)
            target = Path(str(receipt["target_logical"]))
            manifest = backups.get(str(receipt["backup_id"]))
            assert isinstance(manifest, str)
            candidates.append((
                key, target, state_root / manifest, str(item["current_token"])))
        if not candidates:
            return {"schema_version": 1, "restored": []}
        operation_id = os.urandom(16).hex()
        journal_path, journal = substrate.create_journal(
            state_root, action="skill-uninstall",
            plan_digest=str(plan["plan_digest"]), operation_id=operation_id)
        journal, _ = substrate.update_journal(
            journal_path, journal, status="applying")
        restored = []
        rollback: list[tuple[Path, Path, str]] = []
        committed = False
        try:
            for key, target, manifest, token in candidates:
                rollback_manifest, _ = substrate.create_backup(
                    state_root, target, operation_id=operation_id,
                    artifact_id=f"rollback-{len(rollback)}")
                result = substrate.restore_backup(
                    manifest, target, expected_current=token)
                rollback.append((target, rollback_manifest, result.token))
                artifacts.pop(key)
                restored.append(key)
                journal, _ = substrate.update_journal(
                    journal_path, journal, status="applying",
                    step={"artifact": key, "status": "restored"})
            updated = {
                **state, "generation": int(state["generation"]) + 1,
                "artifacts": artifacts,
            }
            substrate.validate_state(updated)
            substrate.atomic_write_json(state_path, updated, expected=state_expected)
            committed = True
            substrate.update_journal(journal_path, journal, status="complete")
        except BaseException as error:
            if not committed:
                for target, manifest, token in reversed(rollback):
                    with contextlib.suppress(Exception):
                        substrate.restore_backup(
                            manifest, target, expected_current=token)
            with contextlib.suppress(substrate.GlobalError):
                substrate.update_journal(
                    journal_path, journal, status="failed", error=str(error))
            raise
    return {"schema_version": 1, "restored": restored}


def _root_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--home")
    parser.add_argument("--config-root")
    parser.add_argument("--state-root")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="statutor global skill")
    children = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "plan", "apply", "sync", "uninstall"):
        child = children.add_parser(name)
        _root_arguments(child)
        child.add_argument("--json", action="store_true")
        if name in {"plan", "apply", "sync"}:
            child.add_argument("--adopt-identical", action="store_true")
    imported = children.add_parser("import")
    _root_arguments(imported)
    imported.add_argument("path", type=Path)
    imported.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    roots = substrate.resolve_roots(
        home=args.home, config_root=args.config_root, state_root=args.state_root)
    try:
        if args.command == "import":
            preview = skill_import_plan(roots, args.path)
            print(json.dumps(preview, sort_keys=True, indent=2), file=sys.stderr)
            result = import_skill(roots, args.path)
        elif args.command == "status":
            result = skill_status(roots)
        elif args.command == "plan":
            result = skill_plan(roots, adopt_identical=args.adopt_identical)
        elif args.command in {"apply", "sync"}:
            preview = skill_plan(roots, adopt_identical=args.adopt_identical)
            print(json.dumps(preview, sort_keys=True, indent=2), file=sys.stderr)
            result = apply_skills(roots, adopt_identical=args.adopt_identical)
        else:
            preview = skill_uninstall_plan(roots)
            print(json.dumps(preview, sort_keys=True, indent=2), file=sys.stderr)
            result = uninstall_skills(roots)
    except substrate.GlobalError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, indent=2 if args.json else None))
    return 0
