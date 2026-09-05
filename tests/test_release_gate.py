"""Fast checks for release metadata; the full artifact gate runs in CI."""

from __future__ import annotations

import json
import importlib.util
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
        "python": "0.5.0",
        "plugin": "0.5.0",
        "npm": "0.1.1",
        "cargo": "0.1.1",
    }


def test_python_and_plugin_versions_must_match(tmp_path: Path) -> None:
    for relative in (
        "pyproject.toml",
        ".claude-plugin/plugin.json",
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
    with pytest.raises(RuntimeError, match="Python 0.5.0 != Claude plugin 9.9.9"):
        release_gate.versions(tmp_path)


def test_release_tag_must_match_python_version() -> None:
    release_gate._check_tag("v0.4.0", "0.4.0")
    with pytest.raises(RuntimeError, match="v0.3.0 != package version v0.4.0"):
        release_gate._check_tag("v0.3.0", "0.4.0")
