"""Fast checks for release metadata; the full artifact gate runs in CI."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "statutor_release_gate", ROOT / "scripts" / "release_gate.py")
assert SPEC is not None and SPEC.loader is not None
release_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_gate)


def test_release_versions_are_explicit_and_compatible() -> None:
    assert release_gate.versions(ROOT) == {
        "python": "0.7.4",
        "plugin": "0.7.4",
        "antigravity": "0.7.4",
        "npm": "0.2.0",
        "cargo": "0.1.2",
    }


def test_python_and_plugin_versions_must_match(tmp_path: Path) -> None:
    for relative in (
        "pyproject.toml",
        ".claude-plugin/plugin.json",
        "adapters/antigravity/plugin.json",
        "adapters/opencode/package.json",
        "crates/statutor/Cargo.toml",
        "crates/statutor/Cargo.lock",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    plugin = tmp_path / ".claude-plugin/plugin.json"
    data = json.loads(plugin.read_text(encoding="utf-8"))
    data["version"] = "9.9.9"
    plugin.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Python 0.7.4 != Claude plugin 9.9.9"):
        release_gate.versions(tmp_path)


def test_antigravity_version_must_match_python(tmp_path: Path) -> None:
    for relative in (
        "pyproject.toml", ".claude-plugin/plugin.json",
        "adapters/antigravity/plugin.json", "adapters/opencode/package.json",
        "crates/statutor/Cargo.toml", "crates/statutor/Cargo.lock",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    plugin = tmp_path / "adapters/antigravity/plugin.json"
    data = json.loads(plugin.read_text())
    data["version"] = "9.9.9"
    plugin.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="Antigravity"):
        release_gate.versions(tmp_path)


def test_release_tag_must_match_python_version() -> None:
    release_gate._check_tag("v0.4.0", "0.4.0")
    with pytest.raises(RuntimeError, match="v0.3.0 != package version v0.4.0"):
        release_gate._check_tag("v0.3.0", "0.4.0")


def test_candidate_snapshot_keeps_policy_baseline_and_excludes_untracked_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-c", "user.name=Release test", "-c", "user.email=test@statutor.invalid", *args],
            cwd=repo, text=True)

    git("init", "-q", "-b", "main")
    (repo / ".statutor.yaml").write_text(
        "governed:\n  - pattern: NOTES.md\n    policy: append_only\n")
    (repo / "NOTES.md").write_text("original\n")
    git("add", ".")
    git("commit", "-qm", "baseline")
    (repo / "NOTES.md").write_text("rewritten\n")
    git("add", "NOTES.md")
    (repo / "test_untracked.py").write_text("raise RuntimeError('untracked')\n")
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    monkeypatch.setattr(release_gate, "ROOT", repo)
    release_gate._candidate_tree(snapshot)
    assert (snapshot / "NOTES.md").read_text() == "rewritten\n"
    assert not (snapshot / "test_untracked.py").exists()
    result = subprocess.run(
        [sys.executable, str(ROOT / "core/statutor_core.py"), "staged", str(snapshot)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "append-only" in result.stdout


def test_source_gate_uses_original_exact_tree_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import conformance_scenarios as scenarios

    repo = tmp_path / "repo"
    repo.mkdir()
    scenarios.s52_exact_tree_receipt_authorizes_policy_change(repo)
    policy = repo / ".statutor.yaml"
    policy.write_bytes(policy.read_bytes().rstrip().replace(
        b"hard_max_lines: 200", b"hard_max_lines: 199") + b"\n")
    subprocess.run(["git", "add", ".statutor.yaml"], cwd=repo, check=True)
    tree = subprocess.check_output(["git", "write-tree"], cwd=repo, text=True).strip()
    subprocess.run([
        sys.executable, str(ROOT / "core/statutor_core.py"), "trust", "approve", str(repo),
        "--decision", "D-0015", "--reason", "release fixture", "--confirm-tree", tree,
    ], check=True, capture_output=True)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    monkeypatch.setattr(release_gate, "ROOT", repo)
    release_gate._candidate_tree(snapshot)
    (snapshot / "core").mkdir()
    (snapshot / "core/statutor_core.py").write_bytes((ROOT / "core/statutor_core.py").read_bytes())
    original_run = release_gate._run
    floor_results = []

    def run_floor_only(command, **kwargs):
        if "staged" in command:
            floor_results.append(original_run(command, **kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(release_gate, "_run", run_floor_only)
    release_gate._verify_source(snapshot, tmp_path)
    assert len(floor_results) == 1
