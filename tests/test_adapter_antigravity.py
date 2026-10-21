"""Tests for Statutor Google Antigravity adapter and harness compatibility."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import statutor_core as kernel
import statutor_worker as worker

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_ROOT = REPO_ROOT / "adapters" / "antigravity"


def _batch_chunk(old: str, new: str, start: int = 1, end: int = 1) -> dict:
    return {
        "StartLine": start, "EndLine": end,
        "TargetContent": old, "ReplacementContent": new,
    }


@pytest.mark.parametrize(
    "filename,body,chunks,denied",
    [
        ("plans/archive/probe.md", "old\n", [_batch_chunk("old", "new")], True),
        ("DECISIONS.md", "settled\n", [_batch_chunk("settled", "changed")], True),
        ("DECISIONS.md", "settled\n", [_batch_chunk("settled", "settled\nnew")], False),
        ("TASKS.md", "- [ ] T-0001 keep\n", [_batch_chunk("T-0001", "T-0002")], True),
        ("TASKS.md", "- [ ] T-0001 keep\n", [_batch_chunk("[ ]", "[x]")], False),
        ("AGENTS.md", "old\n", [_batch_chunk("old", "new\n" * 201)], True),
        ("HANDOFF.md", "## Goal\nold\n", [_batch_chunk("## Goal", "removed")], True),
        ("notes/plain.md", "old\n", [_batch_chunk("old", "new")], False),
    ],
)
def test_batch_edits_obey_complete_candidate_policy(
    tmp_path: Path, filename: str, body: str, chunks: list[dict], denied: bool,
) -> None:
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    reason = kernel.validate(
        "multi_replace_file_content",
        {"TargetFile": str(path), "ReplacementChunks": chunks},
        str(tmp_path),
    )
    assert (reason is not None) is denied


@pytest.mark.parametrize("chunks", [
    [], None, "invalid", [{}],
    [_batch_chunk("missing", "new")],
    [_batch_chunk("old", "new", 2, 1)],
    [_batch_chunk("old", "new", True, 1)],
    [_batch_chunk("old", "new"), _batch_chunk("old", "other")],
])
def test_batch_edit_refuses_unproved_governed_candidate(tmp_path: Path, chunks) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("old\n", encoding="utf-8")
    assert kernel.validate(
        "multi_replace_file_content",
        {"TargetFile": str(path), "ReplacementChunks": chunks},
        str(tmp_path),
    ) is not None


def test_batch_edits_reconstruct_original_disjoint_line_ranges(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("same\nkeep\nsame\n", encoding="utf-8")
    payload = {
        "TargetFile": str(path),
        "ReplacementChunks": [
            _batch_chunk("same", "first", 1, 1),
            _batch_chunk("same", "last", 3, 3),
        ],
    }
    assert kernel.validate("multi_replace_file_content", payload, str(tmp_path)) is None
    payload["ReplacementChunks"] = [_batch_chunk("same", "ambiguous", 1, 3)]
    assert kernel.validate("multi_replace_file_content", payload, str(tmp_path)) is not None


def test_native_batch_event_denies_frozen_write(tmp_path: Path) -> None:
    kernel.run_init(str(tmp_path))
    event = {
        "workspacePaths": [str(tmp_path)],
        "toolCall": {
            "name": "multi_replace_file_content",
            "args": {
                "TargetFile": str(tmp_path / "plans/archive/probe.md"),
                "ReplacementChunks": [_batch_chunk("old", "new")],
            },
        },
    }
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "core/statutor_core.py"), "hook"],
        input=json.dumps(event), text=True, capture_output=True, check=True,
    )
    assert json.loads(result.stdout)["decision"] == "deny"


def test_batch_tool_is_registered() -> None:
    matcher = json.loads((ADAPTER_ROOT / "hooks.json").read_text())["statutor"]["PreToolUse"][0]["matcher"]
    assert "multi_replace_file_content" in matcher.split("|")


# --------------------------------------------------------------------------
# 1. Payload & tool normalization
# --------------------------------------------------------------------------

def test_norm_maps_antigravity_pascal_case_keys():
    payload = {
        "TargetFile": "/path/to/file.md",
        "TargetContent": "old",
        "ReplacementContent": "new",
        "CodeContent": "content",
        "CommandLine": "echo 1",
        "AllowMultiple": True,
        "Overwrite": True,
        "Append": False,
    }
    normed = kernel._norm(payload)
    assert normed["file_path"] == "/path/to/file.md"
    assert normed["old_string"] == "old"
    assert normed["new_string"] == "new"
    assert normed["content"] == "content"
    assert normed["command"] == "echo 1"
    assert normed["replace_all"] is True
    assert normed["overwrite"] is True
    assert normed["append"] is False


def test_validate_accepts_antigravity_tool_names(tmp_path: Path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / ".statutor.yaml").write_text("bash_guard: true\n")
    (ledger / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001 — First\n**Status:** accepted\n")

    # run_command -> bash guard
    denial = kernel.validate(
        "run_command",
        {"CommandLine": "echo 'bad' >> DECISIONS.md"},
        str(ledger),
    )
    assert denial is not None
    assert "shell write touching governed file" in denial

    # write_to_file -> write
    # overwrite_bounded with Append=True is denied
    (ledger / "HANDOFF.md").write_text("# HANDOFF\n\n## Goal\nfoo\n")
    denial = kernel.validate(
        "write_to_file",
        {"TargetFile": "HANDOFF.md", "CodeContent": "appended", "Append": True},
        str(ledger),
    )
    assert denial is not None
    assert "overwrite-bounded. Appending is denied" in denial

    # replace_file_content -> edit
    # editing settled decision is denied
    denial = kernel.validate(
        "replace_file_content",
        {
            "TargetFile": "DECISIONS.md",
            "TargetContent": "## D-0001 — First",
            "ReplacementContent": "## D-0001 — Changed",
            "AllowMultiple": False,
        },
        str(ledger),
    )
    assert denial is not None
    assert "DECISIONS.md is append-only" in denial


def test_write_to_file_append_to_append_only_allowed(tmp_path: Path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / ".statutor.yaml").write_text("bash_guard: true\n")
    (ledger / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001 — Init\n**Status:** accepted\n")

    # Appending a new D-record is allowed
    denial = kernel.validate(
        "write_to_file",
        {
            "TargetFile": "DECISIONS.md",
            "CodeContent": "\n## D-0002 — Next\n**Status:** accepted\n",
            "Append": True,
        },
        str(ledger),
    )
    assert denial is None


def test_write_to_file_frozen_denied(tmp_path: Path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / ".statutor.yaml").write_text("bash_guard: true\n")
    arch = ledger / "plans" / "archive"
    arch.mkdir(parents=True)
    (arch / "old_plan.md").write_text("# Old plan\n")

    denial = kernel.validate(
        "write_to_file",
        {"TargetFile": "plans/archive/old_plan.md", "CodeContent": "touch"},
        str(ledger),
    )
    assert denial is not None
    assert "frozen" in denial


# --------------------------------------------------------------------------
# 2. Hook protocol: PreToolUse with Antigravity schema
# --------------------------------------------------------------------------

def test_hook_pre_tool_use_antigravity_denial(monkeypatch, capsys, tmp_path: Path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / ".statutor.yaml").write_text("bash_guard: true\n")

    event = {
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "rm -rf DECISIONS.md"},
        },
        "stepIdx": 1,
        "workspacePaths": [str(ledger)],
        "conversationId": "test-conv-123",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    exit_code = kernel.run_hook()
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["decision"] == "deny"
    assert "[statutor]" in out["reason"]


def test_hook_pre_tool_use_antigravity_allow(monkeypatch, capsys, tmp_path: Path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / ".statutor.yaml").write_text("bash_guard: true\n")

    event = {
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "pytest -q"},
        },
        "stepIdx": 2,
        "workspacePaths": [str(ledger)],
        "conversationId": "test-conv-123",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    exit_code = kernel.run_hook()
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["decision"] == "allow"


def test_hook_pre_tool_use_outside_ledger_allows(monkeypatch, capsys, tmp_path: Path):
    non_ledger = tmp_path / "other"
    non_ledger.mkdir()

    event = {
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "echo 'x' >> DECISIONS.md"},
        },
        "stepIdx": 3,
        "workspacePaths": [str(non_ledger)],
        "conversationId": "test-conv-456",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    exit_code = kernel.run_hook()
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["decision"] == "allow"


def test_hook_fails_open_on_malformed_input(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    exit_code = kernel.run_hook()
    assert exit_code == 0
    assert capsys.readouterr().out == ""


# --------------------------------------------------------------------------
# 3. Hook protocol: Stop with Antigravity schema
# --------------------------------------------------------------------------

def test_hook_stop_antigravity_clean_ledger(monkeypatch, capsys, tmp_path: Path):
    ledger = tmp_path / "ledger"
    kernel.run_init(str(ledger))
    capsys.readouterr()

    event = {
        "executionNum": 1,
        "terminationReason": "model_stop",
        "fullyIdle": True,
        "workspacePaths": [str(ledger)],
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    exit_code = kernel.run_hook()
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["decision"] == "allow"


def test_hook_stop_antigravity_drift_continues_first_time(monkeypatch, capsys, tmp_path: Path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / ".statutor.yaml").write_text("bash_guard: true\n")
    # Missing required sections is an ERROR drift
    (ledger / "HANDOFF.md").write_text("# HANDOFF\nlast_verified: 2026-01-01 by test\n")

    event = {
        "executionNum": 1,
        "terminationReason": "model_stop",
        "fullyIdle": True,
        "workspacePaths": [str(ledger)],
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    exit_code = kernel.run_hook()
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["decision"] == "continue"
    assert "statutor-doctor found drift" in out["reason"]


def test_hook_stop_antigravity_drift_bounded_to_one_continuation(monkeypatch, capsys, tmp_path: Path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / ".statutor.yaml").write_text("bash_guard: true\n")
    (ledger / "HANDOFF.md").write_text("# HANDOFF\nlast_verified: 2026-01-01 by test\n")

    # executionNum > 1: already continued once
    event = {
        "executionNum": 2,
        "terminationReason": "model_stop",
        "fullyIdle": True,
        "workspacePaths": [str(ledger)],
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    exit_code = kernel.run_hook()
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["decision"] == "allow"


def test_hook_stop_antigravity_outside_workspace_allows(monkeypatch, capsys):
    event = {
        "executionNum": 1,
        "terminationReason": "model_stop",
        "fullyIdle": True,
        "workspacePaths": [],
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    exit_code = kernel.run_hook()
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["decision"] == "allow"


def test_hook_pre_tool_use_outside_workspace_without_cwd_allows(monkeypatch, capsys):
    event = {
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "echo 'x'"},
        },
        "stepIdx": 1,
        "workspacePaths": [],
        "conversationId": "test-conv-no-ws",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    exit_code = kernel.run_hook()
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["decision"] == "allow"


# --------------------------------------------------------------------------
# 4. Worker provenance & capabilities
# --------------------------------------------------------------------------

def test_antigravity_registered_in_worker_capabilities():
    assert "antigravity" in worker.HARNESSES
    assert "gemini" in worker.HARNESSES
    caps = worker.all_capabilities()
    assert "antigravity" in caps["capabilities"]
    assert "gemini" in caps["capabilities"]

    ag_caps = worker.host_capabilities("antigravity")
    assert ag_caps["harness"] == "antigravity"
    assert ag_caps["proves_mutation"] is False
    assert ag_caps["proves_completion"] is False
    assert ag_caps["role_signal"] is False

    gemini_caps = worker.host_capabilities("gemini")
    assert gemini_caps["harness"] == "gemini"


def test_handoff_attribution_accepts_antigravity():
    text = (
        "# HANDOFF\n\n"
        "last_verified: 2026-10-01 by pytest\n"
        "last_worker: antigravity\n"
        "last_machine: 0123456789abcdef0123456789abcdef\n"
        "handoff_id: h_12345\n"
        "supersedes: none\n\n"
        "## Goal\ntest\n\n"
        "## Last verified state\ntest\n\n"
        "## Next action\ntest\n\n"
        "## Gotchas\nnone\n\n"
        "## Do not touch\nnone\n"
    )
    problems = worker.validate_handoff_metadata(text)
    assert problems == []


# --------------------------------------------------------------------------
# 5. Plugin structure and bundle validation
# --------------------------------------------------------------------------

def test_plugin_manifest_valid():
    manifest_path = ADAPTER_ROOT / "plugin.json"
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["name"] == "statutor"
    assert "description" in data
    assert "suggestedPrompts" in data


def test_hooks_json_valid_schema():
    hooks_path = ADAPTER_ROOT / "hooks.json"
    assert hooks_path.is_file()
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert "statutor" in data
    spec = data["statutor"]
    assert "PreToolUse" in spec
    assert "Stop" in spec
    assert spec["PreToolUse"][0]["matcher"] == "run_command|write_to_file|replace_file_content"
    assert spec["PreToolUse"][0]["hooks"][0]["type"] == "command"
    assert spec["Stop"][0]["type"] == "command"


def test_plugin_rules_agents_md_exists():
    rules_path = ADAPTER_ROOT / "rules" / "AGENTS.md"
    assert rules_path.is_file()
    content = rules_path.read_text(encoding="utf-8")
    assert "The Four Planes" in content
    assert "Constitution" in content
    assert "HANDOFF.md" in content
    assert "DECISIONS.md" in content
    assert "Applicability" in content


def test_plugin_skills_bundle():
    skills_dir = ADAPTER_ROOT / "skills"
    assert skills_dir.is_dir()
    expected_skills = {"statutor", "statutor-init", "statutor-doctor", "handoff", "decide"}
    found_skills = {d.name for d in skills_dir.iterdir() if d.is_dir()}
    assert expected_skills.issubset(found_skills)

    for skill_name in expected_skills:
        skill_file = skills_dir / skill_name / "SKILL.md"
        assert skill_file.is_file(), f"missing SKILL.md for {skill_name}"
        text = skill_file.read_text(encoding="utf-8")
        assert text.startswith("---"), f"missing frontmatter for {skill_name}"
        assert f"name: {skill_name}" in text
        assert "description:" in text
