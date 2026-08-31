"""Hermetic checks for the opt-in current-host E2E harness."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "global_e2e", ROOT / "scripts/global_e2e.py")
assert SPEC is not None and SPEC.loader is not None
global_e2e = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(global_e2e)


def test_hermetic_run_uses_only_temporary_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(global_e2e.shutil, "which", lambda host: f"/fake/{host}")
    monkeypatch.setattr(
        global_e2e, "_version",
        lambda host, binary, env, cwd: global_e2e.EXPECTED_VERSIONS[host])
    monkeypatch.setattr(
        global_e2e, "_codex_probe",
        lambda binary, project, env: {"skill_catalog_entries": 1})
    monkeypatch.setattr(
        global_e2e, "_opencode_probe",
        lambda binary, project, env: {"skill_entries": 1})
    monkeypatch.setattr(
        global_e2e, "_claude_probe",
        lambda binary, project, env: {"offline_discovery_surface": False})
    result = global_e2e.run(["claude", "codex", "opencode"])
    assert result["real_home_mutated"] is False
    assert result["safety"] == {
        "instruction_modified_refused": True,
        "skill_modified_refused": True,
        "uninstall_restored_absence": True,
    }
    assert result["versions"] == global_e2e.EXPECTED_VERSIONS
    assert all(
        item["global_marker_count"] == 1
        for item in result["projections"]["instructions"])


def test_version_probe_refuses_an_untested_host_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    completed = subprocess.CompletedProcess(
        ["codex", "--version"], 0, "codex-cli 9.9.9\n", "")
    monkeypatch.setattr(global_e2e, "_run", lambda *args, **kwargs: completed)
    with pytest.raises(global_e2e.E2EError, match="tested baseline"):
        global_e2e._version("codex", "codex", {}, tmp_path)


def test_fake_environment_rehomes_every_host_state(tmp_path: Path) -> None:
    roots = global_e2e.substrate.resolve_roots(
        home=tmp_path / "home",
        config_root=tmp_path / "config",
        state_root=tmp_path / "state",
        environ={}, platform="posix")
    env = global_e2e._fake_env(tmp_path, roots)
    assert env["HOME"] == roots.home
    assert env["CLAUDE_CONFIG_DIR"] == roots.claude_home
    assert env["CODEX_HOME"] == roots.codex_home
    assert env["XDG_CONFIG_HOME"].startswith(str(tmp_path))
    assert env["XDG_DATA_HOME"].startswith(str(tmp_path))
    assert env["XDG_STATE_HOME"].startswith(str(tmp_path))
    assert env["XDG_CACHE_HOME"].startswith(str(tmp_path))
