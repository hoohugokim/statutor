"""Hermetic checks for the opt-in current-host E2E harness."""

from __future__ import annotations

import importlib.util
import io
import json
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


def test_fake_environment_rehomes_every_host_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    for name in (
        "OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT", "OPENCODE_CONFIG_DIR",
        "OPENCODE_PASSWORD", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY",
        "HTTP_PROXY", "PYTHONPATH", "TMPDIR",
    ):
        monkeypatch.setenv(name, "/real-home/or-secret")
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
    assert env["TMPDIR"].startswith(str(tmp_path))
    assert env["OPENCODE_DISABLE_MODELS_FETCH"] == "1"
    assert env["OTEL_SDK_DISABLED"] == "true"
    assert not any(name in env for name in (
        "OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT", "OPENCODE_CONFIG_DIR",
        "OPENCODE_PASSWORD", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY",
        "HTTP_PROXY", "PYTHONPATH",
    ))


class FakeServer:
    def __init__(self, readiness: str, *, slow_exit: bool = False) -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(readiness)
        self.terminated = False
        self.killed = False
        self.slow_exit = slow_exit

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: int) -> int:
        if self.slow_exit and not self.killed:
            raise subprocess.TimeoutExpired("opencode", timeout)
        return 0

    def kill(self) -> None:
        self.killed = True


def test_opencode_probe_activates_plugins_then_checks_native_skill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    server = FakeServer('{"url":"http://127.0.0.1:41234"}\n')
    env = {"HOME": str(tmp_path / "home")}
    calls = []

    def spawn(command, **kwargs):
        assert command == ["opencode", "serve", "--stdio", "--port", "0"]
        assert kwargs["env"]["OPENCODE_PASSWORD"]
        assert kwargs["env"]["OPENCODE_DISABLE_MODELS_FETCH"] == "1"
        return server

    def run(command, **kwargs):
        calls.append(command)
        assert command[:4] == [
            "opencode", "api", "--server", "http://127.0.0.1:41234"]
        assert command[-2:] == ["--param", f"location[directory]={tmp_path}"]
        fixture = {
            "name": global_e2e.SKILL_NAME,
            "path": str(tmp_path / "home/.agents/skills" /
                        global_e2e.SKILL_NAME / "SKILL.md"),
            "content": "\n# E2E fixture\n",
        }
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"data": [fixture]}), "")

    monkeypatch.setattr(global_e2e.subprocess, "Popen", spawn)
    monkeypatch.setattr(global_e2e, "_run", run)
    result = global_e2e._opencode_probe("opencode", tmp_path, env)
    assert [command[4] for command in calls] == ["model.list", "skill.list"]
    assert result["skill_entries"] == 1
    assert result["skill_content_verified"] is True
    assert server.terminated and not server.killed
    assert server.stdin.closed and server.stdout.closed
    assert "OPENCODE_PASSWORD" not in env


@pytest.mark.parametrize("readiness", [
    "", "not-json\n", '{"url":{}}\n', '{"url":"https://example.com"}\n',
])
def test_opencode_probe_rejects_invalid_server_readiness_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, readiness: str,
) -> None:
    server = FakeServer(readiness)
    monkeypatch.setattr(global_e2e.subprocess, "Popen", lambda *a, **k: server)
    with pytest.raises(global_e2e.E2EError):
        global_e2e._opencode_probe("opencode", tmp_path, {"HOME": str(tmp_path)})
    assert server.terminated


def test_opencode_probe_kills_server_when_api_fails_and_exit_times_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    server = FakeServer('{"url":"http://127.0.0.1:41234"}\n', slow_exit=True)
    monkeypatch.setattr(global_e2e.subprocess, "Popen", lambda *a, **k: server)

    def fail(*args, **kwargs):
        raise global_e2e.E2EError("native API failed")

    monkeypatch.setattr(global_e2e, "_run", fail)
    with pytest.raises(global_e2e.E2EError, match="native API failed"):
        global_e2e._opencode_probe("opencode", tmp_path, {"HOME": str(tmp_path)})
    assert server.terminated and server.killed


def test_opencode_probe_cleans_up_after_readiness_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    server = FakeServer("")

    class TimedOut:
        def put(self, value):
            pass

        def get(self, timeout):
            raise global_e2e.queue.Empty

    monkeypatch.setattr(global_e2e.subprocess, "Popen", lambda *a, **k: server)
    monkeypatch.setattr(global_e2e.queue, "Queue", TimedOut)
    with pytest.raises(global_e2e.E2EError, match="readiness"):
        global_e2e._opencode_probe("opencode", tmp_path, {"HOME": str(tmp_path)})
    assert server.terminated


@pytest.mark.parametrize("catalog", [
    {"data": []},
    {"data": [{"name": global_e2e.SKILL_NAME}] * 2},
    {"data": [{"name": global_e2e.SKILL_NAME, "path": "/real-home/SKILL.md"}]},
    {"data": "invalid"},
])
def test_opencode_probe_rejects_missing_duplicate_or_foreign_skills(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, catalog: object,
) -> None:
    server = FakeServer('{"url":"http://127.0.0.1:41234"}\n')
    monkeypatch.setattr(global_e2e.subprocess, "Popen", lambda *a, **k: server)
    monkeypatch.setattr(global_e2e, "_run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, json.dumps(catalog), ""))
    with pytest.raises(global_e2e.E2EError):
        global_e2e._opencode_probe("opencode", tmp_path, {"HOME": str(tmp_path)})
    assert server.terminated
