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
    assert "rev: v0.5.0" in root
    assert "rev: v0.5.0" in git_adapter
    for stale in ("<path-or-url>", "<this repo>", "<your statutor repo url>", "rev: v0.2.0", "rev: v0.4.0"):
        assert stale not in root
        assert stale not in git_adapter


def test_global_e2e_is_explicit_and_real_home_safe() -> None:
    root = (ROOT / "README.md").read_text(encoding="utf-8")
    script = (ROOT / "scripts/global_e2e.py").read_text(encoding="utf-8")
    assert "python scripts/global_e2e.py --json" in root
    assert "temporary profile" in root
    assert "never mutates the caller's real home" in root
    assert "never points a host at the caller's real home" in script
    assert "never performs a\nmodel or network request" in script


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


def test_automatic_adapters_are_explicit_ledger_only() -> None:
    root = _read("README.md")
    codex = _read("adapters/codex/README.md")
    opencode_doc = _read("adapters/opencode/README.md")
    opencode_source = _read("adapters/opencode/statutor.ts")
    assert "stay silent outside a repository explicitly marked" in root
    assert "nearest `.statutor.yaml` marker" in codex
    assert "statutor check --if-ledger" in opencode_doc
    assert "statutor check --if-ledger" in opencode_source


def test_ci_no_longer_installs_unused_pyyaml() -> None:
    assert "pyyaml" not in _read(".github/workflows/ci.yml").lower()
