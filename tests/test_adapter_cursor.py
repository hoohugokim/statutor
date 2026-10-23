"""Tests for the Cursor hooks.json adapter and kernel mapping."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import statutor_core as kernel
import statutor_worker as worker

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_ROOT = REPO_ROOT / "adapters" / "cursor"


def _cursor_hook(monkeypatch, capsys, event: dict) -> dict:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    assert kernel.run_hook() == 0
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


def test_cursor_write_denies_frozen(monkeypatch, capsys, tmp_path: Path) -> None:
    kernel.run_init(str(tmp_path))
    capsys.readouterr()
    event = {
        "hook_event_name": "preToolUse",
        "tool_name": "Write",
        "tool_input": {
            "path": "plans/archive/probe.md",
            "contents": "touch",
        },
        "cwd": str(tmp_path),
        "workspace_roots": [str(tmp_path)],
    }
    out = _cursor_hook(monkeypatch, capsys, event)
    assert out["permission"] == "deny"
    assert "frozen" in out["agent_message"]


def test_cursor_shell_denies_handoff_redirect(monkeypatch, capsys, tmp_path: Path) -> None:
    kernel.run_init(str(tmp_path))
    capsys.readouterr()
    event = {
        "hook_event_name": "beforeShellExecution",
        "command": "echo x >> HANDOFF.md",
        "cwd": str(tmp_path),
        "workspace_roots": [str(tmp_path)],
    }
    out = _cursor_hook(monkeypatch, capsys, event)
    assert out["permission"] == "deny"
    assert "HANDOFF.md" in out["agent_message"]


def test_cursor_silent_outside_ledger(monkeypatch, capsys, tmp_path: Path) -> None:
    event = {
        "hook_event_name": "preToolUse",
        "tool_name": "Write",
        "tool_input": {"path": "DECISIONS.md", "contents": "x"},
        "cwd": str(tmp_path),
        "workspace_roots": [str(tmp_path)],
    }
    out = _cursor_hook(monkeypatch, capsys, event)
    assert out["permission"] == "allow"


def test_cursor_missing_workspace_allows(monkeypatch, capsys) -> None:
    event = {
        "hook_event_name": "beforeShellExecution",
        "command": "echo x >> HANDOFF.md",
        "workspace_roots": [],
    }
    out = _cursor_hook(monkeypatch, capsys, event)
    assert out["permission"] == "allow"


def test_cursor_mcp_write_denies_append_only(monkeypatch, capsys, tmp_path: Path) -> None:
    kernel.run_init(str(tmp_path))
    capsys.readouterr()
    event = {
        "hook_event_name": "beforeMCPExecution",
        "tool_name": "write",
        "tool_input": json.dumps({
            "file_path": "DECISIONS.md",
            "content": "rewritten\n",
        }),
        "mcp_server_name": "files",
        "cwd": str(tmp_path),
        "workspace_roots": [str(tmp_path)],
    }
    out = _cursor_hook(monkeypatch, capsys, event)
    assert out["permission"] == "deny"
    assert "append-only" in out["agent_message"]


def test_cursor_strreplace_denies_decision_edit(monkeypatch, capsys, tmp_path: Path) -> None:
    kernel.run_init(str(tmp_path))
    capsys.readouterr()
    (tmp_path / "DECISIONS.md").write_text("kept\n", encoding="utf-8")
    event = {
        "hook_event_name": "preToolUse",
        "tool_name": "StrReplace",
        "tool_input": {
            "path": "DECISIONS.md",
            "old_string": "kept",
            "new_string": "gone",
        },
        "cwd": str(tmp_path),
        "workspace_roots": [str(tmp_path)],
    }
    out = _cursor_hook(monkeypatch, capsys, event)
    assert out["permission"] == "deny"
    assert "append-only" in out["agent_message"]


def test_cursor_fail_open_emits_allow_json(monkeypatch, capsys, tmp_path: Path) -> None:
    kernel.run_init(str(tmp_path))
    capsys.readouterr()

    def boom(*_args, **_kwargs):
        raise RuntimeError("kernel bug")

    monkeypatch.setattr(kernel, "_automatic_reason", boom)
    event = {
        "hook_event_name": "preToolUse",
        "tool_name": "Write",
        "tool_input": {"path": "DECISIONS.md", "contents": "x\n"},
        "cwd": str(tmp_path),
        "workspace_roots": [str(tmp_path)],
    }
    out = _cursor_hook(monkeypatch, capsys, event)
    assert out["permission"] == "allow"


def test_cursor_malformed_json_emits_allow(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        '{"hook_event_name": "preToolUse",'))
    assert kernel.run_hook() == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["permission"] == "allow"


def test_cursor_delete_denies_governed(monkeypatch, capsys, tmp_path: Path) -> None:
    kernel.run_init(str(tmp_path))
    capsys.readouterr()
    event = {
        "hook_event_name": "preToolUse",
        "tool_name": "Delete",
        "tool_input": {"path": "DECISIONS.md"},
        "cwd": str(tmp_path),
        "workspace_roots": [str(tmp_path)],
    }
    out = _cursor_hook(monkeypatch, capsys, event)
    assert out["permission"] == "deny"
    assert "delete is denied" in out["agent_message"]


def test_cursor_registered_in_worker_capabilities() -> None:
    assert "cursor" in worker.HARNESSES
    caps = worker.host_capabilities("cursor")
    assert caps["proves_mutation"] is False
    assert "preToolUse" in str(caps["attempt_surface"])


def test_cursor_adapter_hooks_json_exists() -> None:
    data = json.loads((ADAPTER_ROOT / "hooks.json").read_text(encoding="utf-8"))
    assert data["version"] == 1
    for name in ("preToolUse", "beforeShellExecution", "beforeMCPExecution", "stop"):
        assert name in data["hooks"]


def test_repo_dogfoods_cursor_hooks() -> None:
    data = json.loads((REPO_ROOT / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert "preToolUse" in data["hooks"]
    assert "statutor_core.py" in data["hooks"]["preToolUse"][0]["command"]
