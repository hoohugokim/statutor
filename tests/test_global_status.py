"""Unified global status and doctor tests under fake roots."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import statutor_global as substrate
import statutor_global_cli as instructions
import statutor_global_status as diagnostics
import statutor_skills as skills


def _roots(tmp_path: Path) -> substrate.ResolvedRoots:
    roots = substrate.resolve_roots(
        home=tmp_path / "home",
        config_root=tmp_path / "config",
        state_root=tmp_path / "state",
        environ={},
        platform="posix",
    )
    instructions.global_init(roots)
    return roots


def _skill(parent: Path, name: str, content: str = "same") -> Path:
    root = parent / name
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Use {name} for diagnostics.\n"
        "extension: preserved\n---\n\n# Skill\n",
        encoding="utf-8",
    )
    (root / "payload.txt").write_text(content, encoding="utf-8")
    return root


def _codes(result: dict[str, object]) -> set[str]:
    return {str(item["code"]) for item in result["diagnostics"]}


def test_empty_inventory_has_stable_schema_and_no_false_errors(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    result = diagnostics.global_inventory(roots, admin_root=tmp_path / "admin")
    assert list(result) == [
        "schema_version", "operation", "roots", "contracts", "instructions",
        "skills", "diagnostics", "summary",
    ]
    assert [item["status"] for item in result["instructions"]["hosts"]] == [
        "missing", "missing", "missing",
    ]
    assert result["skills"]["catalog"] == {
        "occurrences": 0,
        "unique_names": 0,
        "distinct_descriptions": 0,
        "description_bytes": 0,
        "limit_bytes": 32768,
        "within_limit": True,
        "limit_source": "Statutor diagnostic default; not a host cap",
    }
    assert result["summary"] == {"errors": 0, "warnings": 0}
    assert json.loads(json.dumps(result, sort_keys=True)) == result
    assert diagnostics.global_inventory(
        roots, admin_root=tmp_path / "admin") == result


def test_effective_instruction_precedence_and_budget(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    instructions.apply_instructions(roots, hosts=["claude", "codex"])
    override = Path(roots.codex_home) / "AGENTS.override.md"
    override.write_text("shadowing override", encoding="utf-8")
    codex_config = Path(roots.codex_home) / "config.toml"
    codex_config.write_text("project_doc_max_bytes = 8\n", encoding="utf-8")
    result = diagnostics.global_inventory(roots, admin_root=tmp_path / "admin")
    by_host = {item["host"]: item for item in result["instructions"]["hosts"]}
    assert by_host["codex"]["effective_source"] == str(override)
    assert by_host["codex"]["effective_reason"] == "global-override"
    assert by_host["codex"]["shadowed"] is True
    assert by_host["opencode"]["effective_source"] == str(
        Path(roots.claude_home) / "CLAUDE.md")
    assert by_host["opencode"]["effective_reason"] == "claude-fallback"
    assert result["instructions"]["codex_instruction_budget"] == {
        "limit_bytes": 8,
        "effective_global_bytes": len("shadowing override"),
        "within_limit": False,
    }
    assert {"codex-base-shadowed", "codex-instruction-budget-exceeded"} <= _codes(result)


def test_managed_instruction_drift_and_header_tampering_are_errors(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    instructions.apply_instructions(roots, hosts=["codex"])
    common = Path(roots.config_root) / "AGENTS.md"
    common.write_text("# new common\n", encoding="utf-8")
    result = diagnostics.global_inventory(roots, admin_root=tmp_path / "admin")
    codex = next(item for item in result["instructions"]["hosts"]
                 if item["host"] == "codex")
    assert codex["status"] == "outdated"
    assert "instruction-outdated" in _codes(result)

    target = Path(roots.codex_home) / "AGENTS.md"
    target.write_text("human edit", encoding="utf-8")
    state_path = instructions._state_path(roots)
    state = substrate.load_json(state_path)
    state["artifacts"]["instruction-codex"]["installed_token"] = (
        substrate.fingerprint(target).token)
    state_path.write_bytes(substrate.canonical_json(state))
    result = diagnostics.global_inventory(roots, admin_root=tmp_path / "admin")
    codex = next(item for item in result["instructions"]["hosts"]
                 if item["host"] == "codex")
    assert codex["status"] == "generated-header-invalid"
    assert "instruction-generated-header-invalid" in _codes(result)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO is POSIX-only")
def test_special_instruction_target_is_reported_without_crashing(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    target = Path(roots.codex_home) / "AGENTS.md"
    target.parent.mkdir(parents=True)
    os.mkfifo(target)
    result = diagnostics.global_inventory(roots, admin_root=tmp_path / "admin")
    codex = next(item for item in result["instructions"]["hosts"]
                 if item["host"] == "codex")
    assert codex["status"] == "invalid"
    assert "instruction-target-invalid" in _codes(result)


def test_managed_skills_report_identical_duplicates_and_source_drift(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    skills.import_skill(roots, _skill(tmp_path / "incoming", "demo-skill"))
    skills.apply_skills(roots)
    result = diagnostics.global_inventory(roots, admin_root=tmp_path / "admin")
    duplicate = next(item for item in result["skills"]["duplicates"]
                     if item["name"] == "demo-skill")
    assert duplicate["classification"] == "identical"
    projected = [item for item in result["skills"]["items"]
                 if item["name"] == "demo-skill" and item["scope"] != "canonical"]
    assert [item["ownership"] for item in projected] == ["statutor", "statutor"]
    assert [item["status"] for item in projected] == ["installed", "installed"]

    canonical = Path(roots.config_root) / "skills/demo-skill/payload.txt"
    canonical.write_text("new source", encoding="utf-8")
    result = diagnostics.global_inventory(roots, admin_root=tmp_path / "admin")
    projected = [item for item in result["skills"]["items"]
                 if item["name"] == "demo-skill" and item["scope"] != "canonical"]
    assert [item["status"] for item in projected] == ["outdated", "outdated"]
    assert "skill-outdated" in _codes(result)


def test_fast_status_does_not_compare_canonical_tree_to_entrypoint_digest(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    skills.import_skill(roots, _skill(tmp_path / "incoming", "adoptable"))
    canonical = Path(roots.config_root) / "skills/adoptable"
    for _, target in skills._skill_targets(roots, "adoptable"):
        substrate.atomic_replace_tree(target, canonical, expected=substrate.ABSENT)
    result = diagnostics.global_inventory(roots, admin_root=tmp_path / "admin")
    duplicate = next(item for item in result["skills"]["duplicates"]
                     if item["name"] == "adoptable")
    assert duplicate["classification"] == "identical"
    assert duplicate["hard_conflict"] is False


def test_divergent_legacy_duplicate_and_inventory_only_roots(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    skills.import_skill(roots, _skill(tmp_path / "incoming", "same-name", "canonical"))
    skills.apply_skills(roots)
    _skill(Path(roots.codex_home) / "skills", "same-name", "legacy divergence")
    _skill(Path(roots.opencode_home) / "skills", "native-only")
    plugin = (
        Path(roots.codex_home)
        / "plugins/cache/vendor/plugin/1.0/skills/plugin-only"
    )
    _skill(plugin.parent, plugin.name)
    admin_root = tmp_path / "admin"
    _skill(admin_root, "admin-only")
    result = diagnostics.global_doctor(roots, admin_root=admin_root)
    scopes = {(item["scope"], item["name"])
              for item in result["skills"]["items"]}
    assert {
        ("codex-legacy", "same-name"),
        ("opencode-native", "native-only"),
        ("codex-plugin-cache", "plugin-only"),
        ("codex-admin", "admin-only"),
    } <= scopes
    duplicate = next(item for item in result["skills"]["duplicates"]
                     if item["name"] == "same-name")
    assert duplicate["classification"] == "divergent"
    assert duplicate["hard_conflict"] is False
    assert "skill-inventory-divergent" in _codes(result)


def test_divergence_across_active_opencode_roots_is_a_hard_conflict(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    _skill(Path(roots.portable_skills), "collision", "portable")
    _skill(Path(roots.claude_home) / "skills", "collision", "claude")
    result = diagnostics.global_doctor(roots, admin_root=tmp_path / "admin")
    duplicate = next(item for item in result["skills"]["duplicates"]
                     if item["name"] == "collision")
    assert duplicate["classification"] == "divergent"
    assert duplicate["hard_conflict"] is True
    assert "skill-duplicate-divergent" in _codes(result)


def test_catalog_budget_is_measured_once_per_distinct_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _roots(tmp_path)
    skill = _skill(Path(roots.portable_skills), "budgeted")
    claude = Path(roots.claude_home) / "skills/budgeted"
    substrate.atomic_replace_tree(claude, skill, expected=substrate.ABSENT)
    monkeypatch.setattr(diagnostics, "SKILL_DESCRIPTION_BUDGET_BYTES", 8)
    result = diagnostics.global_doctor(roots, admin_root=tmp_path / "admin")
    catalog = result["skills"]["catalog"]
    assert catalog["distinct_descriptions"] == 1
    assert catalog["within_limit"] is False
    assert "skill-catalog-budget-exceeded" in _codes(result)


def test_foreign_disabled_and_unsafe_skills_are_explained(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    portable = _skill(Path(roots.portable_skills), "foreign-skill")
    lock = Path(roots.home) / ".agents/.skill-lock.json"
    lock.write_text(json.dumps({
        "version": 3, "skills": {"foreign-skill": {"source": "elsewhere"}}
    }), encoding="utf-8")
    disabled = _skill(Path(roots.portable_skills), "disabled-skill")
    config = Path(roots.codex_home) / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "[[skills.config]]\n"
        "path = \"~/.agents/skills/disabled-skill/SKILL.md\"\n"
        "enabled = false\n",
        encoding="utf-8",
    )
    unsafe = _skill(Path(roots.opencode_home) / "skills", "unsafe-skill")
    (unsafe / "escape").symlink_to(tmp_path / "outside")
    result = diagnostics.global_doctor(roots, admin_root=tmp_path / "admin")
    by_name = {item["name"]: item for item in result["skills"]["items"]
               if item["scope"] in {"portable", "opencode-native"}}
    assert by_name["foreign-skill"]["ownership"] == "foreign"
    assert by_name["foreign-skill"]["status"] == "foreign-managed"
    assert by_name["disabled-skill"]["disabled"] is True
    assert by_name["disabled-skill"]["status"] == "disabled"
    assert by_name["unsafe-skill"]["status"] == "invalid"
    assert "skill-invalid" in _codes(result)
    assert portable.is_dir()  # Inventory is read-only.


def test_container_root_symlink_and_orphaned_receipt(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    external = tmp_path / "claude-skills"
    external.mkdir()
    claude_root = Path(roots.claude_home) / "skills"
    claude_root.parent.mkdir(parents=True, exist_ok=True)
    claude_root.symlink_to(external, target_is_directory=True)
    skills.import_skill(roots, _skill(tmp_path / "incoming", "linked-root"))
    skills.apply_skills(roots)
    result = diagnostics.global_inventory(roots, admin_root=tmp_path / "admin")
    root = next(item for item in result["skills"]["roots"]
                if item["scope"] == "claude")
    assert root["container_symlink"] is True
    assert root["real_path"] == str(external)

    portable = Path(roots.portable_skills) / "linked-root"
    for child in portable.iterdir():
        child.unlink()
    portable.rmdir()
    result = diagnostics.global_inventory(roots, admin_root=tmp_path / "admin")
    assert "orphaned-receipt" in _codes(result)


def test_unmanaged_external_skill_symlink_is_visible_but_nested_escape_is_not(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    external = _skill(tmp_path / "external", "linked-skill")
    portable_root = Path(roots.portable_skills)
    portable_root.mkdir(parents=True)
    linked = portable_root / "linked-skill"
    linked.symlink_to(external, target_is_directory=True)
    result = diagnostics.global_doctor(roots, admin_root=tmp_path / "admin")
    item = next(item for item in result["skills"]["items"]
                if item["scope"] == "portable")
    assert item["status"] == "visible"
    assert item["external_symlink"] is True

    (external / "nested-escape").symlink_to(tmp_path / "outside")
    result = diagnostics.global_doctor(roots, admin_root=tmp_path / "admin")
    item = next(item for item in result["skills"]["items"]
                if item["scope"] == "portable")
    assert item["status"] == "invalid"
    assert "skill-invalid" in _codes(result)


def test_invalid_documents_are_doctor_errors_not_status_crashes(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    Path(roots.config_root, "global.json").write_text("{}", encoding="utf-8")
    result = diagnostics.global_doctor(roots, admin_root=tmp_path / "admin")
    assert result["operation"] == "global-doctor"
    assert result["summary"]["errors"] >= 1
    assert "global-config-invalid" in _codes(result)


def test_status_cli_exits_zero_but_doctor_exits_one_on_audit_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots = _roots(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", roots.claude_home)
    monkeypatch.setenv("CODEX_HOME", roots.codex_home)
    monkeypatch.setenv(
        "XDG_CONFIG_HOME", str(Path(roots.opencode_home).parent))
    unsafe = _skill(Path(roots.opencode_home) / "skills", "unsafe-skill")
    (unsafe / "cycle").symlink_to(unsafe, target_is_directory=True)
    args = [
        "--home", roots.home,
        "--config-root", roots.config_root,
        "--state-root", roots.state_root,
        "--json",
    ]
    assert instructions.main(["status", *args]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["summary"]["errors"] == 0
    assert instructions.main(["doctor", *args]) == 1
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["operation"] == "global-doctor"
