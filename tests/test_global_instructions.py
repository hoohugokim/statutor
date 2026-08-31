"""Whole-file global instruction lifecycle, always under fake roots."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import statutor_global as substrate
import statutor_global_cli as lifecycle


ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "core/statutor_core.py"


def _roots(tmp_path: Path) -> substrate.ResolvedRoots:
    return substrate.resolve_roots(
        home=tmp_path / "home",
        config_root=tmp_path / "config",
        state_root=tmp_path / "state",
        environ={},
        platform="posix",
    )


def test_init_only_scaffolds_statutor_sources_and_is_idempotent(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    assert all(item["action"] == "write" for item in lifecycle.init_plan(roots)["actions"])
    first = lifecycle.global_init(roots)
    assert all(item["action"] == "write" for item in first)
    assert Path(roots.config_root, "global.json").is_file()
    assert Path(roots.config_root, "AGENTS.md").is_file()
    assert all(Path(roots.config_root, f"hosts/{host}.md").is_file()
               for host in substrate.HOSTS)
    assert not lifecycle.instruction_target(roots, "claude").exists()
    assert not lifecycle.instruction_target(roots, "codex").exists()
    assert not lifecycle.instruction_target(roots, "opencode").exists()
    second = lifecycle.global_init(roots)
    assert all(item["action"] == "skip" for item in second)


def test_init_preflights_invalid_existing_config_without_partial_writes(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    config = Path(roots.config_root, "global.json")
    config.parent.mkdir(parents=True)
    config.write_text("not json", encoding="utf-8")
    with pytest.raises(substrate.SchemaError):
        lifecycle.global_init(roots)
    assert not Path(roots.config_root, "AGENTS.md").exists()
    assert not Path(roots.state_root, "global-state.json").exists()


def test_plan_apply_status_and_idempotence_for_all_hosts(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    lifecycle.global_init(roots)
    plan = lifecycle.instruction_plan(roots)
    assert [item["action"] for item in plan["items"]] == ["create"] * 3
    result = lifecycle.apply_instructions(roots)
    assert [item["action"] for item in result["items"]] == ["noop"] * 3
    for host in substrate.HOSTS:
        target = lifecycle.instruction_target(roots, host)
        assert target.is_file()
        assert target.read_bytes().startswith(lifecycle.GENERATED_HEADER)
        assert target.stat().st_mode & 0o777 == 0o600
    state_before = substrate.load_json(Path(roots.state_root, "global-state.json"))
    assert set(state_before["artifacts"]) == {
        "instruction-claude", "instruction-codex", "instruction-opencode"
    }
    lifecycle.apply_instructions(roots)
    state_after = substrate.load_json(Path(roots.state_root, "global-state.json"))
    assert state_after["generation"] == state_before["generation"]
    status = lifecycle.global_status(roots)
    assert [item["status"] for item in status["hosts"]] == ["installed"] * 3


def test_unmanaged_conflict_prevents_every_create(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    lifecycle.global_init(roots)
    codex = lifecycle.instruction_target(roots, "codex")
    codex.parent.mkdir(parents=True)
    codex.write_text("human", encoding="utf-8")
    plan = lifecycle.instruction_plan(roots)
    assert [item["action"] for item in plan["items"]] == [
        "create", "conflict", "create"
    ]
    with pytest.raises(substrate.GlobalError, match="nothing changed"):
        lifecycle.apply_instructions(roots)
    assert codex.read_text(encoding="utf-8") == "human"
    assert not lifecycle.instruction_target(roots, "claude").exists()
    assert not lifecycle.instruction_target(roots, "opencode").exists()


def test_adopt_preserves_original_bytes_and_uninstall_restores_target(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    lifecycle.global_init(roots)
    target = lifecycle.instruction_target(roots, "codex")
    target.parent.mkdir(parents=True)
    original = b"# Human Codex instructions\nlast byte stays"
    target.write_bytes(original)
    preview = lifecycle.adoption_plan(roots, "codex")
    assert preview["original_bytes_preserved"] is True
    assert any("behavior may change" in warning for warning in preview["warnings"])
    lifecycle.adopt_instruction(roots, "codex")
    overlay = Path(roots.config_root, "hosts/codex.md")
    assert overlay.read_bytes() == original
    assert original in target.read_bytes()
    assert lifecycle.uninstall_plan(roots, hosts=["codex"])["items"][0][
        "action"] == "restore"
    result = lifecycle.uninstall_instructions(roots, hosts=["codex"])
    assert result["restored"] == ["codex"]
    assert target.read_bytes() == original
    assert overlay.read_bytes() == original
    assert lifecycle.uninstall_plan(roots, hosts=["codex"])["items"][0][
        "action"] == "noop"


def test_source_update_is_cas_guarded_and_target_edit_refuses_mutation(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    lifecycle.global_init(roots)
    lifecycle.apply_instructions(roots, hosts=["claude"])
    common = Path(roots.config_root, "AGENTS.md")
    common.write_text("# Revised common\n", encoding="utf-8")
    plan = lifecycle.instruction_plan(roots, hosts=["claude"])
    assert plan["items"][0]["action"] == "update"
    lifecycle.apply_instructions(roots, hosts=["claude"])
    target = lifecycle.instruction_target(roots, "claude")
    assert b"# Revised common" in target.read_bytes()
    target.write_text("human edit", encoding="utf-8")
    assert lifecycle.instruction_plan(roots, hosts=["claude"])["items"][0][
        "action"] == "conflict"
    with pytest.raises(substrate.GlobalError):
        lifecycle.apply_instructions(roots, hosts=["claude"])
    with pytest.raises(substrate.GlobalError, match="modified"):
        lifecycle.uninstall_instructions(roots, hosts=["claude"])
    assert target.read_text(encoding="utf-8") == "human edit"


def test_precedence_warnings_are_explicit(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    lifecycle.global_init(roots)
    override = Path(roots.codex_home, "AGENTS.override.md")
    override.parent.mkdir(parents=True)
    override.write_text("override", encoding="utf-8")
    claude = lifecycle.instruction_target(roots, "claude")
    claude.parent.mkdir(parents=True)
    claude.write_text("fallback", encoding="utf-8")
    plan = lifecycle.instruction_plan(roots, hosts=["codex", "opencode"])
    assert any("shadows" in warning for warning in plan["warnings"])
    assert any("suppresses" in warning for warning in plan["warnings"])


def test_multi_host_apply_rolls_back_earlier_target_on_late_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _roots(tmp_path)
    lifecycle.global_init(roots)
    real_write = substrate.atomic_write_bytes
    codex = lifecycle.instruction_target(roots, "codex")

    def fail_codex(target, content, **kwargs):
        if Path(target) == codex:
            raise substrate.ConcurrentChange("injected concurrent change")
        return real_write(target, content, **kwargs)

    monkeypatch.setattr(substrate, "atomic_write_bytes", fail_codex)
    with pytest.raises(substrate.ConcurrentChange):
        lifecycle.apply_instructions(roots)
    assert not lifecycle.instruction_target(roots, "claude").exists()
    assert not lifecycle.instruction_target(roots, "codex").exists()
    assert not lifecycle.instruction_target(roots, "opencode").exists()
    state = substrate.load_json(Path(roots.state_root, "global-state.json"))
    assert state["artifacts"] == {}


def test_state_cas_failure_rolls_back_installed_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _roots(tmp_path)
    lifecycle.global_init(roots)
    state_path = Path(roots.state_root, "global-state.json")
    real_write_json = substrate.atomic_write_json

    def fail_state(target, data, **kwargs):
        if Path(target) == state_path:
            raise substrate.ConcurrentChange("injected state change")
        return real_write_json(target, data, **kwargs)

    monkeypatch.setattr(substrate, "atomic_write_json", fail_state)
    with pytest.raises(substrate.ConcurrentChange):
        lifecycle.apply_instructions(roots, hosts=["claude"])
    assert not lifecycle.instruction_target(roots, "claude").exists()
    assert substrate.load_json(state_path)["artifacts"] == {}


def test_cli_dispatch_uses_only_explicit_fake_roots(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    config = tmp_path / "config"
    state = tmp_path / "state"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "decoy-home"),
        "XDG_CONFIG_HOME": str(tmp_path / "decoy-config"),
        "XDG_STATE_HOME": str(tmp_path / "decoy-state"),
    }
    for name in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):
        env.pop(name, None)
    base = [
        sys.executable, str(KERNEL), "global",
    ]
    roots = [
        "--home", str(fake_home),
        "--config-root", str(config),
        "--state-root", str(state),
    ]
    initialized = subprocess.run(
        base + ["init"] + roots + ["--json"],
        cwd=ROOT, env=env, capture_output=True, text=True)
    assert initialized.returncode == 0, initialized.stderr
    applied = subprocess.run(
        base + ["apply"] + roots + ["--host", "codex", "--json"],
        cwd=ROOT, env=env, capture_output=True, text=True)
    assert applied.returncode == 0, applied.stderr
    data = json.loads(applied.stdout)
    assert data["items"][0]["action"] == "noop"
    assert (fake_home / ".codex/AGENTS.md").is_file()
    assert not (tmp_path / "decoy-home/.codex/AGENTS.md").exists()
