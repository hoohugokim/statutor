"""T-0040: optional HANDOFF worker/machine metadata, doctor diagnostics,
completion validation, and read-only reconciliation guidance."""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import statutor_core
import statutor_doctor
import statutor_worker as worker


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path: Path, name: str, handoff: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / ".statutor.yaml").write_text("bash_guard: true\n")
    (root / "HANDOFF.md").write_text(handoff)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    return root


def _handoff(stamp: str, block: str) -> str:
    return (
        "# HANDOFF\n\n"
        f"last_verified: {stamp} by `pytest`\n"
        f"{block}\n"
        "## Goal\ntest\n\n"
        "## Last verified state\ntest\n\n"
        "## Next action\ntest\n\n"
        "## Gotchas\nnone\n\n"
        "## Do not touch\nnone\n"
    )


VALID_BLOCK = ("last_worker: unknown\nlast_machine: unknown\n"
               "handoff_id: none\nsupersedes: none\n")
TODAY = date.today().isoformat()


def _state(tmp_path: Path, name: str = "state") -> Path:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ledger(tmp_path: Path, handoff: str) -> Path:
    root = tmp_path / "ledger"
    root.mkdir(exist_ok=True)
    for name, content in {
        "AGENTS.md": "# AGENTS\n\nShort constitution for tests.\n",
        "HANDOFF.md": handoff,
        "DECISIONS.md": ("# DECISIONS\n\n## D-0001 — Example\n"
                         "**Status:** accepted\n**Context:** x\n"
                         "**Decision:** y\n**Consequences:** z\n"),
        "TASKS.md": "# TASKS\n\n- [ ] T-0001 example task\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    return root


def _doctor_out(root: Path) -> tuple[str, int]:
    statutor_doctor.check(str(root))
    out = ("WARN  " + "\nWARN  ".join(statutor_doctor.warnings)
           + "\nERROR " + "\nERROR ".join(statutor_doctor.errors))
    return out, 1 if statutor_doctor.errors else 0


# --------------------------------------------------------------------------
# scaffold
# --------------------------------------------------------------------------

def test_template_carries_attribution_defaults() -> None:
    content = statutor_core.TEMPLATES["HANDOFF.md"]
    for line in ("last_worker: unknown", "last_machine: unknown",
                 "handoff_id: none", "supersedes: none"):
        assert line in content
    assert content.count("\n") + 1 <= 40


def test_template_handoff_is_doctor_clean(tmp_path: Path) -> None:
    template = statutor_core.TEMPLATES["HANDOFF.md"]
    root = _ledger(tmp_path, template)
    out, code = _doctor_out(root)
    assert code == 0
    assert "attribution" not in out


# --------------------------------------------------------------------------
# doctor diagnostics
# --------------------------------------------------------------------------

def test_old_handoff_without_block_warns_only(tmp_path: Path) -> None:
    root = _ledger(tmp_path, _handoff(TODAY, ""))
    out, code = _doctor_out(root)
    assert code == 0
    assert "no v0.5 worker attribution block" in out
    assert "still valid" in out


def test_partial_block_is_tolerated(tmp_path: Path) -> None:
    root = _ledger(tmp_path, _handoff(TODAY, "handoff_id: hA\nsupersedes: h0\n"))
    out, code = _doctor_out(root)
    assert code == 0
    assert "attribution" not in out


@pytest.mark.parametrize("block,fragment", [
    ("last_worker: klingon\nhandoff_id: none\nsupersedes: none\n",
     "last_worker 'klingon' is not a stable harness id"),
    ("last_machine: not-hex\nhandoff_id: none\nsupersedes: none\n",
     "last_machine 'not-hex' is neither"),
    ("handoff_id: 'has spaces'\nsupersedes: none\n",
     "handoff_id"),
    ("handoff_id: h1\nsupersedes: 'bad id!'\n", "supersedes"),
    ("handoff_id: none\nsupersedes: none\nlast_machine_label: " + "x" * 129 + "\n",
     "last_machine_label"),
    ("handoff_id: none\nsupersedes: none\nlast_machine_label:\n",
     "last_machine_label"),
])
def test_malformed_block_errors(tmp_path: Path, block: str, fragment: str) -> None:
    root = _ledger(tmp_path, _handoff(TODAY, block))
    out, code = _doctor_out(root)
    assert code == 1
    assert fragment in out


# --------------------------------------------------------------------------
# completion validation
# --------------------------------------------------------------------------

def test_complete_accepts_matching_attribution(tmp_path: Path) -> None:
    state = _state(tmp_path)
    machine, _ = worker.ensure_machine(state)
    repo = _repo(tmp_path, "repo", _handoff(TODAY, VALID_BLOCK))
    begun = worker.worker_begin(state, str(repo), harness="claude")
    (repo / "HANDOFF.md").write_text(_handoff(
        TODAY,
        f"last_worker: claude\nlast_machine: {machine['machine_id']}\n"
        "handoff_id: h1\nsupersedes: none\n"))
    done = worker.worker_complete(state, str(repo),
                                  session_id=begun["session"]["session_id"])
    assert done["record"]["handoff_id"] == "h1"


def test_complete_rejects_foreign_machine(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo", _handoff(TODAY, VALID_BLOCK))
    begun = worker.worker_begin(state, str(repo), harness="claude")
    (repo / "HANDOFF.md").write_text(_handoff(
        TODAY, "last_worker: claude\nlast_machine: " + "0" * 32 + "\n"
        "handoff_id: h1\nsupersedes: none\n"))
    with pytest.raises(worker.WorkerError, match="another machine"):
        worker.worker_complete(state, str(repo),
                               session_id=begun["session"]["session_id"])


def test_complete_rejects_mismatched_worker(tmp_path: Path) -> None:
    state = _state(tmp_path)
    machine, _ = worker.ensure_machine(state)
    repo = _repo(tmp_path, "repo", _handoff(TODAY, VALID_BLOCK))
    begun = worker.worker_begin(state, str(repo), harness="claude")
    (repo / "HANDOFF.md").write_text(_handoff(
        TODAY, f"last_worker: codex\nlast_machine: {machine['machine_id']}\n"
        "handoff_id: h1\nsupersedes: none\n"))
    with pytest.raises(worker.WorkerError, match="does not match the session"):
        worker.worker_complete(state, str(repo),
                               session_id=begun["session"]["session_id"])


def test_complete_rejects_malformed_block(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo", _handoff(TODAY, VALID_BLOCK))
    begun = worker.worker_begin(state, str(repo), harness="claude")
    (repo / "HANDOFF.md").write_text(_handoff(
        TODAY, "last_worker: klingon\nhandoff_id: h1\nsupersedes: none\n"))
    with pytest.raises(worker.WorkerError, match="malformed"):
        worker.worker_complete(state, str(repo),
                               session_id=begun["session"]["session_id"])


# --------------------------------------------------------------------------
# compare attribution + reconciliation guidance
# --------------------------------------------------------------------------

def test_compare_reports_attribution_and_guidance(tmp_path: Path) -> None:
    state = _state(tmp_path)
    machine, _ = worker.ensure_machine(state)
    mid = machine["machine_id"]
    repo = _repo(tmp_path, "repo", _handoff(
        TODAY, f"last_worker: claude\nlast_machine: {mid}\n"
        "handoff_id: h0\nsupersedes: none\n"))
    _git(repo, "checkout", "-qb", "sibling")
    (repo / "HANDOFF.md").write_text(_handoff(
        TODAY, f"last_worker: codex\nlast_machine: {mid}\n"
        "handoff_id: hA\nsupersedes: h0\n"))
    _git(repo, "commit", "-qam", "sibling handoff")
    _git(repo, "checkout", "-q", "-")
    (repo / "HANDOFF.md").write_text(_handoff(
        TODAY, f"last_worker: claude\nlast_machine: {mid}\n"
        "handoff_id: hB\nsupersedes: h0\n"))
    _git(repo, "commit", "-qam", "ours handoff")
    result = worker.worker_compare(state, str(repo), ref="sibling")
    assert result["classification"] == "sibling"
    assert result["ours"]["last_worker"] == "claude"
    assert result["theirs"]["last_worker"] == "codex"
    assert result["ours"]["last_machine"] == mid
    assert result["reconciliation_must_supersede"] == ["hA", "hB"]
    assert any("hA" in step and "hB" in step
               for step in result["reconciliation_guidance"])
    assert "never" in result["note"]
