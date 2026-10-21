"""Portable Agent Skill lifecycle tests under explicit fake roots."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import statutor_global as substrate
import statutor_global_cli as instructions
import statutor_skills as skills


def _roots(tmp_path: Path) -> substrate.ResolvedRoots:
    roots = substrate.resolve_roots(
        home=tmp_path / "home", config_root=tmp_path / "config",
        state_root=tmp_path / "state", environ={}, platform="posix")
    instructions.global_init(roots)
    return roots


def _skill(parent: Path, name: str = "demo-skill", *, description: str = "Use for demos.") -> Path:
    root = parent / name
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\ncustom-field: preserved\n---\n\n# Demo\n",
        encoding="utf-8")
    (root / "reference.txt").write_text("reference", encoding="utf-8")
    return root


def test_skill_metadata_validates_core_and_preserves_extensions(tmp_path: Path) -> None:
    root = _skill(tmp_path)
    assert skills.skill_metadata(root) == {
        "name": "demo-skill", "description": "Use for demos."
    }
    assert "custom-field: preserved" in (root / "SKILL.md").read_text()


@pytest.mark.parametrize(
    "body,fragment",
    [
        ("name: Bad_Name\ndescription: valid", "name violates"),
        ("name: other\ndescription: valid", "parent directory"),
        ("name: demo-skill\ndescription:", "1-1024"),
    ],
)
def test_skill_metadata_rejects_invalid_core(
    tmp_path: Path, body: str, fragment: str
) -> None:
    root = tmp_path / "demo-skill"
    root.mkdir()
    (root / "SKILL.md").write_text(f"---\n{body}\n---\n", encoding="utf-8")
    with pytest.raises(substrate.SchemaError, match=fragment):
        skills.skill_metadata(root)


def test_block_description_is_supported(tmp_path: Path) -> None:
    root = tmp_path / "demo-skill"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: >-\n  Does demos.\n  Use for tests.\n---\n",
        encoding="utf-8")
    assert skills.skill_metadata(root)["description"] == "Does demos. Use for tests."


def test_skill_root_symlink_is_rejected(tmp_path: Path) -> None:
    real = _skill(tmp_path / "real")
    linked = tmp_path / "demo-skill"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(substrate.UnsafeTree, match="real directory"):
        skills.skill_metadata(linked)


@pytest.mark.parametrize("scope", ["portable", "claude"])
@pytest.mark.parametrize("operation", ["apply", "uninstall"])
def test_retargeted_skill_parent_is_never_mutated(
    tmp_path: Path, scope: str, operation: str,
) -> None:
    roots = _roots(tmp_path)
    skills.import_skill(roots, _skill(tmp_path / "incoming"))
    skills.apply_skills(roots)
    target = dict(skills._skill_targets(roots, "demo-skill"))[scope]
    original = tmp_path / "original-skills"
    foreign = tmp_path / "foreign-skills"
    target.parent.rename(original)
    shutil.copytree(original, foreign)
    target.parent.symlink_to(foreign, target_is_directory=True)
    foreign_before = substrate.fingerprint(foreign).token
    state_before = Path(roots.state_root, "global-state.json").read_bytes()
    Path(roots.config_root, "skills/demo-skill/reference.txt").write_text("updated")

    plan = (skills.skill_plan if operation == "apply"
            else skills.skill_uninstall_plan)(roots)
    item = next(item for item in plan["items"] if item["scope"] == scope)
    assert item["action"] == "conflict"
    with pytest.raises(substrate.GlobalError):
        (skills.apply_skills if operation == "apply"
         else skills.uninstall_skills)(roots)
    assert substrate.fingerprint(foreign).token == foreign_before
    assert Path(roots.state_root, "global-state.json").read_bytes() == state_before


def test_identical_adoption_refuses_parent_retarget_after_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots = _roots(tmp_path)
    skills.import_skill(roots, _skill(tmp_path / "incoming"))
    canonical = Path(roots.config_root, "skills/demo-skill")
    target = Path(roots.portable_skills, "demo-skill")
    substrate.atomic_replace_tree(target, canonical, expected=substrate.ABSENT)
    original = tmp_path / "original-skills"
    foreign = tmp_path / "foreign-skills"
    shutil.copytree(target.parent, foreign)
    foreign_before = substrate.fingerprint(foreign).token
    state_path = Path(roots.state_root, "global-state.json")
    state_before = state_path.read_bytes()
    real_backup = substrate.create_backup

    def retarget_after_backup(state_root, path, **kwargs):
        result = real_backup(state_root, path, **kwargs)
        if Path(path) == target:
            target.parent.rename(original)
            target.parent.symlink_to(foreign, target_is_directory=True)
        return result

    monkeypatch.setattr(substrate, "create_backup", retarget_after_backup)
    with pytest.raises(substrate.GlobalError):
        skills.apply_skills(roots, adopt_identical=True)
    assert substrate.fingerprint(foreign).token == foreign_before
    assert state_path.read_bytes() == state_before


def test_skill_install_and_restore_support_a_stable_symlink_parent(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    skills.import_skill(roots, _skill(tmp_path / "incoming"))
    parent = Path(roots.portable_skills)
    real_parent = tmp_path / "real-skills"
    real_parent.mkdir()
    parent.parent.mkdir(parents=True)
    parent.symlink_to(real_parent, target_is_directory=True)
    skills.apply_skills(roots)
    assert (real_parent / "demo-skill").is_dir()
    skills.uninstall_skills(roots)
    assert parent.is_symlink()
    assert not (real_parent / "demo-skill").exists()


def test_import_is_local_new_only_and_exact(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    source = _skill(tmp_path / "incoming")
    result = skills.import_skill(roots, source)
    canonical = Path(str(result["canonical"]))
    assert substrate.tree_digest(canonical) == substrate.tree_digest(source)
    with pytest.raises(substrate.GlobalError, match="already exists"):
        skills.import_skill(roots, source)


def test_plan_apply_sync_and_uninstall_dual_projections(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    source = _skill(tmp_path / "incoming")
    skills.import_skill(roots, source)
    assert [item["action"] for item in skills.skill_plan(roots)["items"]] == [
        "create", "create"
    ]
    skills.apply_skills(roots)
    status = skills.skill_status(roots)
    assert [item["status"] for item in status["items"]] == [
        "installed", "installed"
    ]
    assert status["duplicates"] == [
        {"name": "demo-skill", "classification": "identical"}
    ]
    canonical = Path(roots.config_root, "skills/demo-skill")
    (canonical / "reference.txt").write_text("updated", encoding="utf-8")
    assert [item["action"] for item in skills.skill_plan(roots)["items"]] == [
        "update", "update"
    ]
    skills.apply_skills(roots)
    assert all(
        (target / "reference.txt").read_text() == "updated"
        for _, target in skills._skill_targets(roots, "demo-skill"))
    restored = skills.uninstall_skills(roots)
    assert len(restored["restored"]) == 2
    assert all(not target.exists() for _, target in skills._skill_targets(roots, "demo-skill"))
    assert canonical.is_dir()


def test_identical_unmanaged_requires_explicit_adoption(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    source = _skill(tmp_path / "incoming")
    skills.import_skill(roots, source)
    canonical = Path(roots.config_root, "skills/demo-skill")
    portable = Path(roots.portable_skills, "demo-skill")
    substrate.atomic_replace_tree(portable, canonical, expected=substrate.ABSENT)
    plan = skills.skill_plan(roots)
    assert plan["items"][0]["action"] == "conflict"
    adopted = skills.skill_plan(roots, adopt_identical=True)
    assert adopted["items"][0]["action"] == "adopt-identical"
    skills.apply_skills(roots, adopt_identical=True)
    result = skills.uninstall_skills(roots)
    assert len(result["restored"]) == 2
    assert portable.is_dir()  # Initial identical unmanaged tree is restored.


def test_foreign_lock_blocks_every_projection_for_name(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    skills.import_skill(roots, _skill(tmp_path / "incoming"))
    lock = Path(roots.home, ".agents/.skill-lock.json")
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({
        "version": 3, "skills": {"demo-skill": {"source": "foreign"}}
    }), encoding="utf-8")
    plan = skills.skill_plan(roots)
    assert plan["foreign_locked"] == ["demo-skill"]
    assert [item["action"] for item in plan["items"]] == [
        "foreign-managed", "foreign-managed"
    ]
    skills.apply_skills(roots)
    assert all(not target.exists() for _, target in skills._skill_targets(roots, "demo-skill"))


def test_foreign_lock_appearing_later_blocks_uninstall(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    skills.import_skill(roots, _skill(tmp_path / "incoming"))
    skills.apply_skills(roots)
    lock = Path(roots.home, ".agents/.skill-lock.json")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({
        "version": 3, "skills": {"demo-skill": {"source": "foreign"}}
    }), encoding="utf-8")
    assert all(
        item["action"] == "conflict"
        for item in skills.skill_uninstall_plan(roots)["items"])
    with pytest.raises(substrate.GlobalError, match="nothing changed"):
        skills.uninstall_skills(roots)
    assert all(target.is_dir() for _, target in skills._skill_targets(roots, "demo-skill"))


def test_apply_rolls_back_targets_when_state_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _roots(tmp_path)
    skills.import_skill(roots, _skill(tmp_path / "incoming"))
    state_path = instructions._state_path(roots)
    original_write = substrate.atomic_write_json

    def fail_state(path: Path, data: object, **kwargs: object):
        if Path(path) == state_path:
            raise substrate.ConcurrentChange("injected state race")
        return original_write(path, data, **kwargs)

    monkeypatch.setattr(substrate, "atomic_write_json", fail_state)
    with pytest.raises(substrate.ConcurrentChange, match="injected"):
        skills.apply_skills(roots)
    assert all(not target.exists() for _, target in skills._skill_targets(roots, "demo-skill"))


def test_mutating_cli_commands_print_plans_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    roots = _roots(tmp_path)
    source = _skill(tmp_path / "incoming")
    root_args = [
        "--home", roots.home,
        "--config-root", roots.config_root,
        "--state-root", roots.state_root,
    ]
    assert skills.main(["import", *root_args, str(source), "--json"]) == 0
    captured = capsys.readouterr()
    assert '"operation": "skill-import"' in captured.err
    assert skills.main(["apply", *root_args, "--json"]) == 0
    captured = capsys.readouterr()
    assert '"operation": "skill-apply"' in captured.err
    assert skills.main(["uninstall", *root_args, "--json"]) == 0
    captured = capsys.readouterr()
    assert '"operation": "skill-uninstall"' in captured.err


def test_divergent_or_modified_target_is_never_overwritten(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    skills.import_skill(roots, _skill(tmp_path / "incoming"))
    skills.apply_skills(roots)
    portable = Path(roots.portable_skills, "demo-skill")
    (portable / "reference.txt").write_text("human edit", encoding="utf-8")
    plan = skills.skill_plan(roots)
    assert plan["items"][0]["action"] == "conflict"
    assert plan["duplicates"][0]["classification"] == "divergent"
    with pytest.raises(substrate.GlobalError, match="nothing changed"):
        skills.apply_skills(roots)
    with pytest.raises(substrate.GlobalError, match="modified"):
        skills.uninstall_skills(roots)
    assert (portable / "reference.txt").read_text() == "human edit"
