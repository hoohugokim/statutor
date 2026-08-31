#!/usr/bin/env python3
"""Read-only effective inventory and doctor for Statutor's global layer."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path

import statutor_global as substrate
import statutor_global_cli as lifecycle
import statutor_skills as skill_lifecycle


CODEX_DEFAULT_INSTRUCTION_BYTES = 32 * 1024
SKILL_DESCRIPTION_BUDGET_BYTES = 32 * 1024
CONTRACT_BASELINES = {
    "claude": "2.1.251",
    "codex": "0.151.0",
    "opencode": "1.18.20",
}


def _diagnostic(
    diagnostics: list[dict[str, object]],
    level: str,
    code: str,
    message: str,
    *,
    path: Path | None = None,
) -> None:
    item: dict[str, object] = {
        "code": code,
        "level": level,
        "message": message,
    }
    if path is not None:
        item["path"] = str(path)
    diagnostics.append(item)


def _nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _toml_string(raw: str) -> str | None:
    raw = raw.strip()
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, str) else None
    if raw.startswith("'") and len(raw) >= 2 and raw.endswith("'"):
        return raw[1:-1]
    return None


def _codex_config_facts(
    roots: substrate.ResolvedRoots,
    diagnostics: list[dict[str, object]],
) -> tuple[int, set[str]]:
    """Read only the two documented settings needed by diagnostics."""
    path = Path(roots.codex_home) / "config.toml"
    if not path.exists():
        return CODEX_DEFAULT_INSTRUCTION_BYTES, set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        _diagnostic(
            diagnostics, "warning", "codex-config-unreadable",
            f"cannot inspect Codex config: {error}", path=path)
        return CODEX_DEFAULT_INSTRUCTION_BYTES, set()

    limit = CODEX_DEFAULT_INSTRUCTION_BYTES
    disabled: set[str] = set()
    skill_entry: dict[str, object] | None = None

    def finish_entry() -> None:
        if not skill_entry or skill_entry.get("enabled") is not False:
            return
        value = skill_entry.get("path")
        if isinstance(value, str):
            if value == "~" or value.startswith("~/"):
                candidate = Path(roots.home) / value[2:]
            else:
                candidate = Path(value)
            if not candidate.is_absolute():
                candidate = Path(roots.codex_home) / candidate
            disabled.add(str(Path(os.path.abspath(candidate))))

    for line in lines:
        stripped = line.strip()
        if stripped == "[[skills.config]]":
            finish_entry()
            skill_entry = {}
            continue
        if stripped.startswith("[[") or stripped.startswith("["):
            finish_entry()
            skill_entry = None
            continue
        match = re.fullmatch(
            r"project_doc_max_bytes\s*=\s*([0-9][0-9_]*)\s*(?:#.*)?",
            stripped,
        )
        if match:
            limit = int(match.group(1).replace("_", ""))
            continue
        if skill_entry is None or "=" not in stripped:
            continue
        key, raw = (part.strip() for part in stripped.split("=", 1))
        if key == "path":
            value = _toml_string(raw)
            if value is not None:
                skill_entry["path"] = value
        elif key == "enabled" and raw.split("#", 1)[0].strip() in {
            "true", "false",
        }:
            skill_entry["enabled"] = (
                raw.split("#", 1)[0].strip() == "true")
    finish_entry()
    if limit <= 0:
        _diagnostic(
            diagnostics, "warning", "codex-budget-invalid",
            "project_doc_max_bytes is not positive; using the 32 KiB default",
            path=path)
        limit = CODEX_DEFAULT_INSTRUCTION_BYTES
    return limit, disabled


def _load_documents(
    roots: substrate.ResolvedRoots,
    diagnostics: list[dict[str, object]],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    config = None
    state = None
    for label, path, validator in (
        ("config", lifecycle._config_path(roots), substrate.validate_config),
        ("state", lifecycle._state_path(roots), substrate.validate_state),
    ):
        try:
            value = validator(substrate.load_json(path))
        except substrate.GlobalError as error:
            _diagnostic(
                diagnostics, "error", f"global-{label}-invalid", str(error),
                path=path)
            continue
        if label == "config":
            config = value
        else:
            state = value
    return config, state


def _instruction_inventory(
    roots: substrate.ResolvedRoots,
    config: dict[str, object] | None,
    state: dict[str, object] | None,
    diagnostics: list[dict[str, object]],
    *,
    hosts: list[str] | None,
    codex_budget: int,
) -> dict[str, object]:
    budget = codex_budget
    if config is None or state is None:
        return {
            "hosts": [],
            "codex_instruction_budget": {
                "limit_bytes": budget, "effective_global_bytes": 0,
                "within_limit": True,
            },
        }
    try:
        selected = lifecycle._selected_hosts(config, hosts)
    except substrate.GlobalError as error:
        _diagnostic(diagnostics, "error", "host-selection-invalid", str(error))
        selected = []
    artifacts = state["artifacts"]
    assert isinstance(artifacts, dict)
    items = []
    codex_effective_bytes = 0
    for host in selected:
        target = lifecycle.instruction_target(roots, host)
        current_error = None
        try:
            current = substrate.fingerprint(target)
        except substrate.GlobalError as error:
            current_error = str(error)
            current = substrate.Fingerprint("unsafe", None)
            _diagnostic(
                diagnostics, "error", "instruction-target-invalid",
                f"{host}: {error}", path=target)
        receipt = artifacts.get(f"instruction-{host}")
        desired_digest = None
        source_error = None
        try:
            common, overlay = lifecycle._source_paths(roots, config, host)
            desired = lifecycle.render_instruction(
                common.read_bytes(), overlay.read_bytes(), host)
            desired_digest = substrate.content_digest(desired)
        except (OSError, substrate.GlobalError) as error:
            source_error = str(error)
            _diagnostic(
                diagnostics, "error", "instruction-source-invalid",
                f"{host}: {error}")
        if receipt is None:
            ownership = "unmanaged"
            if current_error:
                status = "invalid"
            else:
                status = (
                    "missing" if current.kind == substrate.ABSENT else "unmanaged")
        else:
            assert isinstance(receipt, dict)
            ownership = "statutor"
            receipt_target = str(receipt["target_logical"])
            common_path, _ = lifecycle._source_paths(roots, config, host)
            real_target = None
            if current.kind != substrate.ABSENT:
                try:
                    real_target = str(target.resolve(strict=True))
                except (OSError, RuntimeError):
                    pass
            if (
                receipt_target != str(target.absolute())
                or str(receipt["source_logical"]) != str(common_path.absolute())
                or (
                    real_target is not None
                    and str(receipt["target_real"]) != real_target
                )
            ):
                status = "receipt-mismatch"
            elif current.kind == substrate.ABSENT:
                status = "missing"
            elif current.token != receipt["installed_token"]:
                status = "modified"
            elif (
                current.kind != "file"
                or not target.read_bytes().startswith(lifecycle.GENERATED_HEADER)
            ):
                status = "generated-header-invalid"
            elif desired_digest is None:
                status = "source-invalid"
            elif current.digest != desired_digest:
                status = "outdated"
            else:
                status = "installed"
        effective_path: Path | None = target if _nonempty_file(target) else None
        effective_reason = "native"
        shadowed = False
        if host == "codex":
            override = Path(roots.codex_home) / "AGENTS.override.md"
            if _nonempty_file(override):
                effective_path = override
                effective_reason = "global-override"
                shadowed = _nonempty_file(target)
                if shadowed:
                    _diagnostic(
                        diagnostics, "warning", "codex-base-shadowed",
                        "Codex AGENTS.override.md shadows the managed base",
                        path=override)
            codex_effective_bytes = (
                effective_path.stat().st_size if effective_path is not None else 0)
        elif host == "opencode" and effective_path is None:
            fallback = Path(roots.claude_home) / "CLAUDE.md"
            if _nonempty_file(fallback):
                effective_path = fallback
                effective_reason = "claude-fallback"
        if status in {
            "missing", "modified", "source-invalid", "receipt-mismatch",
            "generated-header-invalid",
        } and receipt is not None:
            _diagnostic(
                diagnostics, "error", f"instruction-{status}",
                f"managed {host} instruction is {status}", path=target)
        elif status == "outdated":
            _diagnostic(
                diagnostics, "warning", "instruction-outdated",
                f"managed {host} instruction is behind its source", path=target)
        items.append({
            "host": host,
            "target": str(target),
            "target_token": current.token,
            "ownership": ownership,
            "status": status,
            "desired_digest": desired_digest,
            "source_error": source_error,
            "target_error": current_error,
            "effective_source": (
                str(effective_path) if effective_path is not None else None),
            "effective_reason": effective_reason if effective_path else "none",
            "shadowed": shadowed,
        })
    within = codex_effective_bytes <= budget
    if not within:
        _diagnostic(
            diagnostics, "error", "codex-instruction-budget-exceeded",
            f"effective Codex global instructions use {codex_effective_bytes} "
            f"bytes, above the configured {budget}-byte cap")
    return {
        "hosts": items,
        "codex_instruction_budget": {
            "limit_bytes": budget,
            "effective_global_bytes": codex_effective_bytes,
            "within_limit": within,
        },
    }


def _root_specs(
    roots: substrate.ResolvedRoots,
    config: dict[str, object] | None,
    admin_root: Path | None,
) -> list[dict[str, object]]:
    canonical = Path(roots.config_root) / "skills"
    if config is not None:
        skills = config["skills"]
        assert isinstance(skills, dict)
        canonical = Path(roots.config_root) / str(skills["source"])
    return [
        {"scope": "canonical", "path": canonical, "kind": "shallow",
         "contract": "statutor-source", "hosts": []},
        {"scope": "portable", "path": Path(roots.portable_skills),
         "kind": "shallow", "contract": "user", "hosts": ["codex", "opencode"]},
        {"scope": "claude", "path": Path(roots.claude_home) / "skills",
         "kind": "shallow", "contract": "user", "hosts": ["claude", "opencode"]},
        {"scope": "opencode-native", "path": Path(roots.opencode_home) / "skills",
         "kind": "shallow", "contract": "host-native", "hosts": ["opencode"]},
        {"scope": "codex-legacy", "path": Path(roots.codex_home) / "skills",
         "kind": "shallow", "contract": "compatibility-inventory", "hosts": ["codex"],
         "exclude": [".system"]},
        {"scope": "codex-system", "path": Path(roots.codex_home) / "skills/.system",
         "kind": "shallow", "contract": "system-cache", "hosts": ["codex"]},
        {"scope": "codex-plugin-cache", "path": Path(roots.codex_home) / "plugins/cache",
         "kind": "plugin", "contract": "plugin-cache-inventory", "hosts": ["codex"]},
        {"scope": "codex-admin", "path": admin_root or Path("/etc/codex/skills"),
         "kind": "shallow", "contract": "admin", "hosts": ["codex"]},
    ]


def _inside(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((str(path), str(root))) == str(root)
    except ValueError:
        return False


def _skill_ownership(
    scope: str,
    name: str,
    token: str,
    state: dict[str, object] | None,
    foreign: set[str],
) -> tuple[str, str]:
    if scope == "canonical":
        return "human", "source"
    if name in foreign:
        return "foreign", "foreign-managed"
    if scope in {"codex-plugin-cache", "codex-system", "codex-admin"}:
        return scope.removeprefix("codex-"), "host-owned"
    if state is not None and scope in {"portable", "claude"}:
        artifacts = state["artifacts"]
        assert isinstance(artifacts, dict)
        receipt = artifacts.get(f"skill-{name}-{scope}")
        if isinstance(receipt, dict):
            status = "installed" if token == receipt["installed_token"] else "modified"
            return "statutor", status
    return "unmanaged", "visible"


def _skill_item(
    path: Path,
    spec: dict[str, object],
    state: dict[str, object] | None,
    foreign: set[str],
    disabled: set[str],
    diagnostics: list[dict[str, object]],
    *,
    deep: bool,
) -> dict[str, object]:
    scope = str(spec["scope"])
    logical = Path(os.path.abspath(path))
    name = path.name
    description = None
    digest = None
    digest_kind = None
    real = None
    external_symlink = False
    error = None
    try:
        root_real = Path(str(spec["path"])).resolve(strict=True)
        real_path = path.resolve(strict=True)
        real = str(real_path)
        if not _inside(real_path, root_real):
            external_symlink = path.is_symlink()
            artifacts = state["artifacts"] if state is not None else {}
            assert isinstance(artifacts, dict)
            managed = f"skill-{path.name}-{scope}" in artifacts
            if scope == "canonical" or managed or not external_symlink:
                raise substrate.UnsafeTree("skill root escapes its discovery root")
        artifacts = state["artifacts"] if state is not None else {}
        assert isinstance(artifacts, dict)
        managed = f"skill-{path.name}-{scope}" in artifacts
        full_tree = spec["kind"] != "plugin" and (
            deep or scope == "canonical" or managed)
        metadata = skill_lifecycle.skill_metadata(
            path, validate_tree=full_tree,
            allow_root_symlink=path.is_symlink(), expected_name=path.name)
        name = metadata["name"]
        description = metadata["description"]
        if not full_tree:
            digest = substrate.content_digest((path / "SKILL.md").read_bytes())
            digest_kind = "entrypoint"
        else:
            digest = substrate.tree_digest(path)
            digest_kind = "tree"
        token = (
            substrate.fingerprint(path).token
            if full_tree else f"entrypoint:{digest}")
    except (OSError, RuntimeError, substrate.GlobalError) as caught:
        error = str(caught)
        token = "unsafe"
        _diagnostic(
            diagnostics,
            "warning" if scope in {
                "codex-plugin-cache", "codex-system", "codex-admin",
            } else "error",
            "skill-invalid",
            f"{scope}/{path.name}: {caught}", path=path)
    ownership, status = _skill_ownership(
        scope, name, token, state, foreign)
    if ownership == "statutor" and state is not None:
        artifacts = state["artifacts"]
        assert isinstance(artifacts, dict)
        receipt = artifacts.get(f"skill-{name}-{scope}")
        assert isinstance(receipt, dict)
        if str(receipt["target_logical"]) != str(logical):
            status = "receipt-mismatch"
        elif real is not None and str(receipt["target_real"]) != real:
            status = "realpath-changed"
    entrypoint = str(logical / "SKILL.md")
    is_disabled = entrypoint in disabled or (
        real is not None and str(Path(real) / "SKILL.md") in disabled)
    if is_disabled:
        status = "disabled"
    if ownership == "statutor" and status in {
        "modified", "receipt-mismatch", "realpath-changed",
    }:
        _diagnostic(
            diagnostics, "error", f"skill-{status}",
            f"managed {scope} skill {name} is {status}", path=path)
    return {
        "name": name,
        "scope": scope,
        "path": str(logical),
        "real_path": real,
        "external_symlink": external_symlink,
        "hosts": list(spec["hosts"]),
        "contract": spec["contract"],
        "ownership": ownership,
        "status": "invalid" if error else status,
        "digest": digest,
        "digest_kind": digest_kind,
        "description": description,
        "description_bytes": (
            len(description.encode("utf-8")) if description is not None else None),
        "disabled": is_disabled,
        "error": error,
    }


def _scan_root(
    spec: dict[str, object],
    state: dict[str, object] | None,
    foreign: set[str],
    disabled: set[str],
    diagnostics: list[dict[str, object]],
    *,
    deep: bool,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    path = Path(str(spec["path"]))
    root_info = {
        "scope": spec["scope"],
        "path": str(path),
        "contract": spec["contract"],
        "hosts": list(spec["hosts"]),
        "status": "missing",
        "real_path": None,
        "container_symlink": path.is_symlink(),
    }
    if not path.exists():
        if path.is_symlink():
            root_info["status"] = "broken-symlink"
            _diagnostic(
                diagnostics, "error", "skill-root-broken",
                f"{spec['scope']} root is a broken symlink", path=path)
        return root_info, []
    try:
        real = path.resolve(strict=True)
        if not real.is_dir():
            raise substrate.UnsafeTree("skill discovery root is not a directory")
        root_info["real_path"] = str(real)
        root_info["status"] = "available"
    except (OSError, RuntimeError, substrate.GlobalError) as error:
        root_info["status"] = "invalid"
        _diagnostic(
            diagnostics, "error", "skill-root-invalid", str(error), path=path)
        return root_info, []

    candidates: list[Path] = []
    if spec["kind"] == "plugin":
        for directory, child_dirs, files in os.walk(path, followlinks=False):
            child_dirs.sort()
            if "SKILL.md" in files and Path(directory).parent.name == "skills":
                candidates.append(Path(directory))
                child_dirs[:] = []  # Skill payloads cannot contain another root.
    else:
        excluded = set(spec.get("exclude", []))
        for child in sorted(path.iterdir(), key=lambda entry: entry.name):
            if child.name in excluded or child.name == ".skill-lock.json":
                continue
            if child.is_dir() or child.is_symlink():
                candidates.append(child)
            else:
                _diagnostic(
                    diagnostics, "warning", "skill-root-extra-entry",
                    f"unexpected non-skill entry in {spec['scope']} root",
                    path=child)
    items = [
        _skill_item(
            candidate, spec, state, foreign, disabled, diagnostics, deep=deep)
        for candidate in candidates
    ]
    return root_info, items


def _skill_inventory(
    roots: substrate.ResolvedRoots,
    config: dict[str, object] | None,
    state: dict[str, object] | None,
    diagnostics: list[dict[str, object]],
    *,
    admin_root: Path | None,
    disabled: set[str],
    deep: bool,
) -> dict[str, object]:
    try:
        foreign = skill_lifecycle.foreign_locked_names(roots)
    except substrate.GlobalError as error:
        foreign = set()
        _diagnostic(
            diagnostics, "error", "foreign-lock-invalid", str(error),
            path=Path(roots.home) / ".agents/.skill-lock.json")
    root_items = []
    skills = []
    for spec in _root_specs(roots, config, admin_root):
        root_info, items = _scan_root(
            spec, state, foreign, disabled, diagnostics, deep=deep)
        root_items.append(root_info)
        skills.extend(items)
    canonical = {
        str(item["name"]): item
        for item in skills
        if item["scope"] == "canonical" and item["digest"] is not None
    }
    for item in skills:
        source = canonical.get(str(item["name"]))
        if item["ownership"] == "statutor" and source is not None and state is not None:
            artifacts = state["artifacts"]
            assert isinstance(artifacts, dict)
            receipt = artifacts.get(
                f"skill-{item['name']}-{item['scope']}")
            assert isinstance(receipt, dict)
            if (
                str(receipt["source_logical"]) != str(source["path"])
                or str(receipt["source_real"]) != str(source["real_path"])
            ):
                item["status"] = "receipt-mismatch"
                _diagnostic(
                    diagnostics, "error", "skill-receipt-mismatch",
                    f"managed {item['scope']} skill {item['name']} "
                    "receipt points at another source",
                    path=Path(str(item["path"])))
        if (
            item["ownership"] == "statutor"
            and item["status"] == "installed"
            and source is not None
            and item["digest"] != source["digest"]
        ):
            item["status"] = "outdated"
            _diagnostic(
                diagnostics, "warning", "skill-outdated",
                f"managed {item['scope']} skill {item['name']} is behind its source",
                path=Path(str(item["path"])))
    skills.sort(key=lambda item: (
        str(item["name"]), str(item["scope"]), str(item["path"])))

    by_name: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_real: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in skills:
        by_name[str(item["name"])].append(item)
        if item["real_path"] is not None:
            by_real[str(item["real_path"])].append(item)
    duplicates = []
    for name, occurrences in sorted(by_name.items()):
        visible = [item for item in occurrences if item["scope"] != "canonical"]
        if len(visible) < 2:
            continue
        comparable: dict[str, set[object]] = defaultdict(set)
        for item in visible:
            if item["digest"] is not None:
                comparable[str(item["digest_kind"])].add(item["digest"])
        if any(item["digest"] is None for item in visible):
            classification = "invalid"
        elif any(len(values) > 1 for values in comparable.values()):
            classification = "divergent"
        elif len(comparable) == 1:
            classification = "identical"
        else:
            classification = "mixed-digest"
        hard_conflict = False
        if classification == "divergent":
            active = [item for item in visible if item["scope"] in {
                "portable", "claude", "opencode-native",
            }]
            hard_conflict = any(
                left["digest"] != right["digest"]
                and left["digest_kind"] == right["digest_kind"]
                and set(left["hosts"]) & set(right["hosts"])
                for index, left in enumerate(active)
                for right in active[index + 1:]
            )
            _diagnostic(
                diagnostics, "error" if hard_conflict else "warning",
                "skill-duplicate-divergent" if hard_conflict
                else "skill-inventory-divergent",
                f"skill name {name} has divergent visible trees")
        duplicates.append({
            "name": name,
            "classification": classification,
            "hard_conflict": classification == "divergent" and hard_conflict,
            "occurrences": [item["path"] for item in visible],
        })
    realpath_collisions = []
    for real, occurrences in sorted(by_real.items()):
        logical = sorted({str(item["path"]) for item in occurrences})
        if len(logical) < 2:
            continue
        names = sorted({str(item["name"]) for item in occurrences})
        classification = "alias" if len(names) == 1 else "name-collision"
        if classification == "name-collision":
            _diagnostic(
                diagnostics, "error", "skill-realpath-name-collision",
                f"one real skill tree has multiple names: {names}",
                path=Path(real))
        realpath_collisions.append({
            "real_path": real,
            "classification": classification,
            "names": names,
            "logical_paths": logical,
        })
    budgeted_descriptions = {
        (str(item["name"]), str(item["description"]))
        for item in skills
        if item["description"] is not None
        and item["scope"] not in {
            "codex-plugin-cache", "codex-system", "codex-admin",
        }
    }
    description_bytes = sum(
        len(description.encode("utf-8"))
        for _, description in budgeted_descriptions)
    within_budget = description_bytes <= SKILL_DESCRIPTION_BUDGET_BYTES
    if not within_budget:
        _diagnostic(
            diagnostics, "warning", "skill-catalog-budget-exceeded",
            f"user/compatibility skill descriptions use {description_bytes} "
            f"bytes, above Statutor's {SKILL_DESCRIPTION_BUDGET_BYTES}-byte "
            "diagnostic budget")
    return {
        "roots": root_items,
        "items": skills,
        "foreign_locked": sorted(foreign),
        "duplicates": duplicates,
        "realpath_collisions": realpath_collisions,
        "catalog": {
            "occurrences": len(skills),
            "unique_names": len(by_name),
            "distinct_descriptions": len(budgeted_descriptions),
            "description_bytes": description_bytes,
            "limit_bytes": SKILL_DESCRIPTION_BUDGET_BYTES,
            "within_limit": within_budget,
            "limit_source": "Statutor diagnostic default; not a host cap",
        },
    }


def global_inventory(
    roots: substrate.ResolvedRoots,
    *,
    hosts: list[str] | None = None,
    admin_root: Path | None = None,
    deep: bool = False,
) -> dict[str, object]:
    diagnostics: list[dict[str, object]] = []
    config, state = _load_documents(roots, diagnostics)
    codex_budget, disabled = _codex_config_facts(roots, diagnostics)
    instructions = _instruction_inventory(
        roots, config, state, diagnostics, hosts=hosts,
        codex_budget=codex_budget)
    skills = _skill_inventory(
        roots, config, state, diagnostics, admin_root=admin_root,
        disabled=disabled, deep=deep)

    if state is not None:
        artifacts = state["artifacts"]
        assert isinstance(artifacts, dict)
        observed = {
            f"instruction-{item['host']}" for item in instructions["hosts"]
        } | {
            f"skill-{item['name']}-{item['scope']}"
            for item in skills["items"]
            if item["scope"] in {"portable", "claude"}
        }
        for artifact in sorted(set(artifacts) - observed):
            _diagnostic(
                diagnostics, "error", "orphaned-receipt",
                f"receipt has no corresponding inventoried artifact: {artifact}")
    diagnostics.sort(key=lambda item: (
        str(item["level"]), str(item["code"]), str(item.get("path", "")),
        str(item["message"])))
    counts = {
        "errors": sum(item["level"] == "error" for item in diagnostics),
        "warnings": sum(item["level"] == "warning" for item in diagnostics),
    }
    return {
        "schema_version": substrate.SCHEMA_VERSION,
        "operation": "global-status",
        "roots": roots.to_json(),
        "contracts": {
            host: {"tested_baseline": version, "runtime_version": None,
                   "probed": False}
            for host, version in CONTRACT_BASELINES.items()
        },
        "instructions": instructions,
        "skills": skills,
        "diagnostics": diagnostics,
        "summary": counts,
    }


def global_doctor(
    roots: substrate.ResolvedRoots,
    *,
    hosts: list[str] | None = None,
    admin_root: Path | None = None,
) -> dict[str, object]:
    result = global_inventory(
        roots, hosts=hosts, admin_root=admin_root, deep=True)
    result["operation"] = "global-doctor"
    return result


def print_human(result: dict[str, object]) -> None:
    instructions = result["instructions"]
    assert isinstance(instructions, dict)
    for item in instructions["hosts"]:
        print(
            f"{str(item['status']).upper():10} instruction/{item['host']} "
            f"effective={item['effective_source'] or '-'}")
    skills = result["skills"]
    assert isinstance(skills, dict)
    for item in skills["items"]:
        print(
            f"{str(item['status']).upper():10} skill/{item['scope']}/"
            f"{item['name']}")
    for item in result["diagnostics"]:
        suffix = f" ({item['path']})" if item.get("path") else ""
        print(
            f"{str(item['level']).upper():7} {item['code']}: "
            f"{item['message']}{suffix}")
    summary = result["summary"]
    print(f"SUMMARY errors={summary['errors']} warnings={summary['warnings']}")
