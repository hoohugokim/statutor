"""Tests for hooks/stop_doctor.py — the Stop hook (T-0005).

No conftest.py: this module bootstraps its own sys.path so `core/` is
importable whether or not the package is installed. The hook is exercised
via subprocess (the actual deployment shape: Claude Code spawns it and
pipes a JSON event on stdin), not by importing it as a module.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import statutor_core

REPO_ROOT = Path(__file__).resolve().parents[1]
STOP_HOOK = REPO_ROOT / "hooks" / "stop_doctor.py"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"


def run_stop_hook(input_str: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(STOP_HOOK)], input=input_str,
                          capture_output=True, text=True)


def _scaffold(root: Path) -> None:
    statutor_core.run_init(str(root))


# --------------------------------------------------------------------------
# hooks.json registration
# --------------------------------------------------------------------------

def test_hooks_json_is_valid_json_with_both_entries():
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    assert "PreToolUse" in data["hooks"]
    assert "Stop" in data["hooks"]


def test_hooks_json_pretooluse_and_stop_share_single_string_command_shape():
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    pre_hook = data["hooks"]["PreToolUse"][0]["hooks"][0]
    stop_hook = data["hooks"]["Stop"][0]["hooks"][0]
    assert pre_hook["type"] == "command"
    assert stop_hook["type"] == "command"
    assert isinstance(pre_hook["command"], str)
    assert isinstance(stop_hook["command"], str)
    assert "args" not in stop_hook
    assert "${CLAUDE_PLUGIN_ROOT}" in stop_hook["command"]
    assert "stop_doctor.py" in stop_hook["command"]


# --------------------------------------------------------------------------
# ledger-presence gate (must be silent outside any statutor ledger)
# --------------------------------------------------------------------------

def test_silent_outside_any_ledger(tmp_path):
    event = {"cwd": str(tmp_path), "stop_hook_active": False}
    result = run_stop_hook(json.dumps(event))
    assert result.returncode == 0
    assert result.stdout == ""


def test_silent_outside_ledger_when_cwd_key_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = subprocess.run([sys.executable, str(STOP_HOOK)],
                            input=json.dumps({"stop_hook_active": False}),
                            capture_output=True, text=True, cwd=str(tmp_path))
    assert result.returncode == 0
    assert result.stdout == ""


def test_generic_agents_only_repo_does_not_opt_into_statutor(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Generic project instructions\n", encoding="utf-8")
    event = {"cwd": str(tmp_path), "stop_hook_active": False}
    result = run_stop_hook(json.dumps(event))
    assert result.returncode == 0
    assert result.stdout == ""


def test_nested_cwd_resolves_marked_ledger_root(tmp_path):
    _scaffold(tmp_path)
    (tmp_path / "TASKS.md").unlink()
    nested = tmp_path / "src" / "deep"
    nested.mkdir(parents=True)
    event = {"cwd": str(nested), "stop_hook_active": False}
    result = run_stop_hook(json.dumps(event))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "missing governed file: TASKS.md" in (
        data["hookSpecificOutput"]["additionalContext"])


# --------------------------------------------------------------------------
# clean ledger / stale-sentinel scaffold: silent
# --------------------------------------------------------------------------

def test_silent_on_clean_scaffolded_ledger_despite_sentinel_stamp(tmp_path):
    """A repo fresh out of `statutor init` ships HANDOFF.md's unfilled
    last_verified: 1970-01-01 sentinel. That alone must not trip the hook."""
    _scaffold(tmp_path)
    event = {"cwd": str(tmp_path), "stop_hook_active": False}
    result = run_stop_hook(json.dumps(event))
    assert result.returncode == 0
    assert result.stdout == ""


def test_real_drift_still_surfaces_alongside_sentinel(tmp_path):
    _scaffold(tmp_path)
    (tmp_path / "TASKS.md").unlink()
    event = {"cwd": str(tmp_path), "stop_hook_active": False}
    result = run_stop_hook(json.dumps(event))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "missing governed file: TASKS.md" in ctx


def test_non_sentinel_stale_handoff_surfaces(tmp_path):
    """Once HANDOFF.md is genuinely re-verified and then goes stale again,
    the stamp is no longer the 1970 sentinel and must be reported."""
    _scaffold(tmp_path)
    handoff = tmp_path / "HANDOFF.md"
    handoff.write_text(
        handoff.read_text(encoding="utf-8").replace("1970-01-01", "2000-01-01"),
        encoding="utf-8",
    )
    event = {"cwd": str(tmp_path), "stop_hook_active": False}
    result = run_stop_hook(json.dumps(event))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "HANDOFF.md last verified" in ctx


# --------------------------------------------------------------------------
# policy-derived state filename (sentinel suppression follows renames)
# --------------------------------------------------------------------------

_CUSTOM_STATE_YAML = """\
bash_guard: true
governed:
  - pattern: AGENTS.md
    policy: constitution
    hard_max_lines: 200
  - pattern: STATUS.md
    policy: overwrite_bounded
    max_lines: 40
    required_sections:
      - "## Goal"
      - "## Last verified state"
      - "## Next action"
      - "## Gotchas"
      - "## Do not touch"
  - pattern: DECISIONS.md
    policy: append_only
  - pattern: TASKS.md
    policy: state
  - pattern: plans/archive/*
    policy: frozen
"""


def _custom_ledger(tmp_path: Path, stamp: str) -> None:
    statutor_core.run_init(str(tmp_path))
    status = (tmp_path / "HANDOFF.md").read_text(encoding="utf-8")
    (tmp_path / "HANDOFF.md").unlink()
    (tmp_path / "STATUS.md").write_text(status.replace("1970-01-01", stamp), encoding="utf-8")
    (tmp_path / ".statutor.yaml").write_text(_CUSTOM_STATE_YAML, encoding="utf-8")


def test_sentinel_suppression_follows_policy_renamed_state_file(tmp_path):
    """A ledger whose overwrite_bounded file is named STATUS.md by policy
    gets the same fresh-scaffold courtesy as HANDOFF.md: one lone sentinel
    WARN must be suppressed, not continued into a spurious stop."""
    _custom_ledger(tmp_path, "1970-01-01")
    event = {"cwd": str(tmp_path), "stop_hook_active": False}
    result = run_stop_hook(json.dumps(event))
    assert result.returncode == 0
    assert result.stdout == ""


def test_real_drift_surfaces_on_policy_renamed_state_file(tmp_path):
    """Suppression must not go over-broad: a renamed state file with a real
    (non-sentinel) stale stamp is still reported, under its actual name."""
    _custom_ledger(tmp_path, "2000-01-01")
    event = {"cwd": str(tmp_path), "stop_hook_active": False}
    result = run_stop_hook(json.dumps(event))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "STATUS.md last verified" in ctx


# --------------------------------------------------------------------------
# JSON shape when it does fire
# --------------------------------------------------------------------------

def test_stale_ledger_emits_parseable_stop_json(tmp_path):
    _scaffold(tmp_path)
    (tmp_path / "TASKS.md").unlink()
    event = {"cwd": str(tmp_path), "stop_hook_active": False}
    result = run_stop_hook(json.dumps(event))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    out = data["hookSpecificOutput"]
    assert out["hookEventName"] == "Stop"
    assert "additionalContext" in out
    assert "systemMessage" in data


# --------------------------------------------------------------------------
# loop guard: stop_hook_active
# --------------------------------------------------------------------------

def test_silent_when_stop_hook_already_active(tmp_path):
    _scaffold(tmp_path)
    (tmp_path / "TASKS.md").unlink()
    event = {"cwd": str(tmp_path), "stop_hook_active": True}
    result = run_stop_hook(json.dumps(event))
    assert result.returncode == 0
    assert result.stdout == ""


# --------------------------------------------------------------------------
# fail-open
# --------------------------------------------------------------------------

def test_fails_open_on_malformed_stdin():
    result = run_stop_hook("{not json")
    assert result.returncode == 0
    assert result.stdout == ""


def test_fails_open_on_empty_stdin():
    result = run_stop_hook("")
    assert result.returncode == 0
    assert result.stdout == ""


def test_fails_open_on_non_object_json():
    result = run_stop_hook("[]")
    assert result.returncode == 0
    assert result.stdout == ""
