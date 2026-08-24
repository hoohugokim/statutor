"""Tests for adapters/hermes/statutor-plugin — the Hermes pre_tool_call adapter (T-0010).

Loads the plugin module the way Hermes would (as a standalone file next to
plugin.yaml) and exercises the tool→kernel mapping. The plugin resolves its
kernel via plain `import statutor_core`, which this suite's sys.path
bootstrap already provides.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))

_PLUGIN = REPO_ROOT / "adapters" / "hermes" / "statutor-plugin" / "__init__.py"
_spec = importlib.util.spec_from_file_location("statutor_hermes_plugin", _PLUGIN)
statutor_hermes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(statutor_hermes)


def test_write_file_over_cap_blocked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = statutor_hermes.pre_tool_call(
        tool_name="write_file",
        args={"path": "AGENTS.md", "content": "x\n" * 201})
    assert result == {"action": "block", "message": result["message"]}
    assert result["message"].startswith("[statutor]")
    assert "hard cap 200" in result["message"]


def test_terminal_bash_guard_blocked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = statutor_hermes.pre_tool_call(
        tool_name="terminal", args={"command": "echo x >> DECISIONS.md"})
    assert result is not None
    assert "append-only" in result["message"] or "shell write" in result["message"]


def test_patch_replace_mode_maps_to_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    blocked = statutor_hermes.pre_tool_call(
        tool_name="patch",
        args={"mode": "replace", "path": "DECISIONS.md",
              "old_string": "kept", "new_string": "gone"})
    assert blocked is not None
    assert "append-only" in blocked["message"]
    allowed = statutor_hermes.pre_tool_call(
        tool_name="patch",
        args={"mode": "replace", "path": "notes/x.md",
              "old_string": "a", "new_string": "b"})
    assert allowed is None


def test_patch_mode_patch_maps_to_apply_patch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    envelope = ("*** Begin Patch\n*** Delete File: DECISIONS.md\n*** End Patch")
    blocked = statutor_hermes.pre_tool_call(
        tool_name="patch", args={"mode": "patch", "patch": envelope})
    assert blocked is not None
    assert "governed (append_only)" in blocked["message"]


def test_unknown_and_non_dict_args_pass_through(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert statutor_hermes.pre_tool_call(tool_name="read_file",
                                         args={"path": "DECISIONS.md"}) is None
    assert statutor_hermes.pre_tool_call(tool_name="terminal", args="not-a-dict") is None


def test_fail_open_when_kernel_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(statutor_hermes, "_kernel_module", lambda: None)
    assert statutor_hermes.pre_tool_call(
        tool_name="write_file",
        args={"path": "AGENTS.md", "content": "x\n" * 500}) is None


def test_register_binds_pre_tool_call():
    class _Ctx:
        def __init__(self):
            self.registered = []

        def register_hook(self, name, cb):
            self.registered.append((name, cb))

    ctx = _Ctx()
    statutor_hermes.register(ctx)
    assert [name for name, _ in ctx.registered] == ["pre_tool_call"]
    assert ctx.registered[0][1] is statutor_hermes.pre_tool_call
