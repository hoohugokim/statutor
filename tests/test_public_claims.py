"""Regression checks for copy-pasteable, capability-accurate public docs."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_install_snippets_use_real_repository_and_supported_pin() -> None:
    root = _read("README.md")
    git_adapter = _read("adapters/git/README.md")
    expected_repo = "https://github.com/hoohugokim/statutor"
    assert f"/plugin marketplace add {expected_repo}" in root
    assert f"repo: {expected_repo}" in root
    assert f"repo: {expected_repo}" in git_adapter
    assert "rev: v0.3.1" in root
    assert "rev: v0.3.1" in git_adapter
    for stale in ("<path-or-url>", "<this repo>", "<your statutor repo url>", "rev: v0.2.0"):
        assert stale not in root
        assert stale not in git_adapter


def test_staged_mode_is_not_advertised_as_server_or_static() -> None:
    root = _read("README.md").lower()
    git_adapter = _read("adapters/git/README.md").lower()
    crate = _read("crates/statutor/README.md").lower()
    assert "pre-commit / pre-receive" not in root
    assert "static `statutor-staged`" not in root
    assert "universal floor" not in root
    assert "running\n`statutor staged` for absolute enforcement" not in git_adapter
    assert "builds a static" not in git_adapter
    assert "not a server-side pre-receive validator" in git_adapter
    assert "does not promise fully static linkage" in crate


def test_codex_and_shared_hook_match_apply_patch() -> None:
    codex = _read("adapters/codex/README.md")
    hooks = json.loads(_read("hooks/hooks.json"))
    assert codex.count('matcher = "^(Bash|apply_patch)$"') == 1
    assert codex.count('"matcher": "^(Bash|apply_patch)$"') == 1
    matcher = hooks["hooks"]["PreToolUse"][0]["matcher"]
    assert matcher == "^(Write|Edit|Bash|apply_patch)$"


def test_ci_no_longer_installs_unused_pyyaml() -> None:
    assert "pyyaml" not in _read(".github/workflows/ci.yml").lower()
