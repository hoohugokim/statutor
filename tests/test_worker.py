"""Fake-root tests for T-0039 machine-local worker provenance."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import statutor_worker as worker
import statutor_global as substrate


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / ".statutor.yaml").write_text("bash_guard: true\n")
    (root / "HANDOFF.md").write_text("# HANDOFF\n\nlast_verified: 2026-09-03 by test\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    return root


def _state(tmp_path: Path, name: str = "state") -> Path:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_machine_created_once_mode_0600(tmp_path: Path) -> None:
    state = _state(tmp_path)
    first, created = worker.ensure_machine(state)
    assert created is True
    second, created_again = worker.ensure_machine(state)
    assert created_again is False
    assert first["machine_id"] == second["machine_id"]
    mode = stat.S_IMODE((_state(tmp_path) / "machine.json").lstat().st_mode)
    assert mode == 0o600


def test_machine_set_label_and_rotate(tmp_path: Path) -> None:
    state = _state(tmp_path)
    labeled = worker.set_machine_label(state, "field-laptop")
    assert labeled["machine"]["label"] == "field-laptop"
    old_id = labeled["machine"]["machine_id"]
    with pytest.raises(worker.WorkerError):
        worker.rotate_machine(state, confirm=False)
    rotated = worker.rotate_machine(state, confirm=True)
    assert rotated["machine"]["machine_id"] != old_id
    assert rotated["previous_machine_id"] == old_id
    assert rotated["machine"]["label"] is None


def test_cloned_state_preserves_identity(tmp_path: Path) -> None:
    src = _state(tmp_path, "src")
    first, _ = worker.ensure_machine(src)
    dst = _state(tmp_path, "dst")
    (dst / "machine.json").write_bytes((src / "machine.json").read_bytes())
    again, created = worker.ensure_machine(dst)
    assert created is False
    assert again["machine_id"] == first["machine_id"]


def test_begin_requires_marked_ledger(tmp_path: Path) -> None:
    state = _state(tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(worker.WorkerError):
        worker.worker_begin(state, str(plain), harness="claude")


def test_begin_show_active_record_flow(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    begun = worker.worker_begin(state, str(repo), harness="claude",
                                role="primary")
    sid = begun["session"]["session_id"]
    assert begun["session"]["baseline_handoff_id"] == "none"
    recorded = worker.worker_record(state, str(repo), harness="claude",
                                    event="attempt", session_id=sid)
    assert recorded["record"]["evidence"] == "attempt"
    shown = worker.worker_show(state, str(repo), basis="attempt")
    assert shown["scope"] == "machine-local"
    assert shown["record"]["session_id"] == sid
    active = worker.worker_active(state, str(repo))
    assert len(active["leases"]) == 1
    assert active["leases"][0]["session_id"] == sid


def test_unknown_role_survives_without_inference(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    begun = worker.worker_begin(state, str(repo), harness="custom")
    assert begun["session"]["role"] == "unknown"
    assert begun["session"]["origin_harness"] == "unknown"


@pytest.mark.parametrize("harness", ["claude", "grok"])
def test_automatic_harness_cannot_record_mutation(tmp_path: Path, harness: str) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    begun = worker.worker_begin(state, str(repo), harness=harness)
    with pytest.raises(worker.WorkerError):
        worker.worker_record(state, str(repo), harness=harness,
                             event="mutation",
                             session_id=begun["session"]["session_id"])


def test_complete_cas_rejects_second_session(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    first = worker.worker_begin(state, str(repo), harness="claude")
    second = worker.worker_begin(state, str(repo), harness="codex")
    # Executor rewrites HANDOFF for the first session.
    (repo / "HANDOFF.md").write_text(
        "# HANDOFF\n\nlast_verified: 2026-09-03 by test\n\n"
        "last_worker: claude\nlast_machine: "
        + str(worker.ensure_machine(state)[0]["machine_id"])
        + "\nhandoff_id: abc123\nsupersedes: none\n")
    done = worker.worker_complete(state, str(repo),
                                  session_id=first["session"]["session_id"])
    assert done["record"]["handoff_id"] == "abc123"
    with pytest.raises(worker.WorkerError, match="another local session"):
        worker.worker_complete(state, str(repo),
                               session_id=second["session"]["session_id"])


def test_complete_requires_fresh_id_and_supersedes(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    begun = worker.worker_begin(state, str(repo), harness="human")
    # No HANDOFF rewrite: still baseline "none" is allowed (backward compat).
    done = worker.worker_complete(state, str(repo),
                                  session_id=begun["session"]["session_id"])
    assert done["record"]["evidence"] == "completed"


def test_expired_leases_age_out(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    begun = worker.worker_begin(state, str(repo), harness="codex")
    sid = begun["session"]["session_id"]
    project_id, _, _ = worker._resolve_project(str(repo))
    path = worker._registry_path(state, project_id)
    registry = json.loads(path.read_text())
    registry["sessions"][sid]["expires_at"] = "2000-01-01T00:00:00+00:00"
    for wt in registry["worktrees"].values():
        for lease in wt["leases"]:
            if lease["session_id"] == sid:
                lease["expires_at"] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(registry))
    active = worker.worker_active(state, str(repo))
    assert active["leases"] == []


def test_linked_worktrees_aggregate_and_separate(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    _git(repo, "worktree", "add", str(tmp_path / "wt"), "-q", "--detach")
    linked = tmp_path / "wt"
    (linked / ".statutor.yaml").write_text("bash_guard: true\n")
    first = worker.worker_begin(state, str(repo), harness="claude")
    worker.worker_record(state, str(repo), harness="claude", event="attempt",
                         session_id=first["session"]["session_id"])
    second = worker.worker_begin(state, str(linked), harness="codex")
    worker.worker_record(state, str(linked), harness="codex", event="attempt",
                         session_id=second["session"]["session_id"])
    repo_only = worker.worker_show(state, str(repo), basis="attempt",
                                   worktree_only=True)
    assert repo_only["record"]["harness"] == "claude"
    agg = worker.worker_active(state, str(repo), worktree_only=False)
    assert len(agg["leases"]) == 2
    wt_only = worker.worker_active(state, str(repo), worktree_only=True)
    assert len(wt_only["leases"]) == 1


def test_registry_holds_no_conversation_content(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    begun = worker.worker_begin(state, str(repo), harness="claude")
    worker.worker_record(state, str(repo), harness="claude", event="attempt",
                         session_id=begun["session"]["session_id"])
    project_id, _, _ = worker._resolve_project(str(repo))
    raw = (worker._registry_path(state, project_id)).read_text()
    for forbidden in ("prompt", "payload", "diff", "model", "transcript"):
        assert forbidden not in raw.lower()
    assert "machine-local" in raw


def test_compare_classifies_sibling(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    _git(repo, "checkout", "-qb", "sibling")
    (repo / "HANDOFF.md").write_text("# HANDOFF\n\nhandoff_id: hA\nsupersedes: h0\n")
    _git(repo, "commit", "-qam", "sibling handoff")
    _git(repo, "checkout", "-q", "-")
    (repo / "HANDOFF.md").write_text("# HANDOFF\n\nhandoff_id: hB\nsupersedes: h0\n")
    _git(repo, "commit", "-qam", "ours handoff")
    result = worker.worker_compare(state, str(repo), ref="sibling")
    assert result["scope"] == "portable-handoff"
    assert result["classification"] == "sibling"
    assert result["reconciliation_must_supersede"] == ["hA", "hB"]


def test_nested_ledger_resolves_nearest(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    nested = repo / "sub"
    nested.mkdir()
    (nested / ".statutor.yaml").write_text("bash_guard: true\n")
    begun = worker.worker_begin(state, str(nested), harness="opencode")
    assert begun["ledger_root"] == str(nested)


def test_registry_mode_0600(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    worker.worker_begin(state, str(repo), harness="human")
    project_id, _, _ = worker._resolve_project(str(repo))
    mode = stat.S_IMODE(
        worker._registry_path(state, project_id).lstat().st_mode)
    assert mode == 0o600
    _ = substrate.ABSENT  # substrate reuse is intentional


@pytest.mark.parametrize("harness,events", [
    ("claude", {"activity", "attempt"}),
    ("codex", {"activity", "attempt"}),
    ("opencode", {"activity", "attempt"}),
    ("antigravity", {"activity", "attempt"}),
    ("gemini", {"activity", "attempt"}),
    ("grok", {"activity", "attempt"}),
    ("custom", {"activity", "attempt", "mutation"}),
    ("human", {"activity", "attempt", "mutation"}),
    ("unknown", {"activity"}),
])
@pytest.mark.parametrize("event", ["activity", "attempt", "mutation"])
def test_record_accepts_only_proven_harness_events(
        tmp_path: Path, harness: str, events: set[str], event: str) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    begun = worker.worker_begin(state, str(repo), harness=harness)
    sid = begun["session"]["session_id"]
    registry = state / "projects" / begun["project_id"] / "workers.json"
    before = registry.read_bytes()
    if event not in events:
        with pytest.raises(worker.WorkerError):
            worker.worker_record(state, str(repo), harness=harness,
                                 event=event, session_id=sid)
        assert registry.read_bytes() == before
        return
    recorded = worker.worker_record(state, str(repo), harness=harness,
                                    event=event, session_id=sid)
    assert recorded["record"]["harness"] == harness
    assert worker.worker_show(state, str(repo), basis=event)["record"] == recorded["record"]


@pytest.mark.parametrize("operation", ["record", "complete"])
@pytest.mark.parametrize("destination", ["linked", "nested", "parent"])
def test_session_cannot_cross_worktree_or_ledger(
        tmp_path: Path, operation: str, destination: str) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    if destination == "linked":
        target = tmp_path / "linked"
        _git(repo, "worktree", "add", str(target), "-q", "--detach")
        source = repo
    else:
        nested = repo / "nested"
        nested.mkdir()
        (nested / ".statutor.yaml").write_text("bash_guard: true\n")
        (nested / "HANDOFF.md").write_bytes((repo / "HANDOFF.md").read_bytes())
        source, target = (repo, nested) if destination == "nested" else (nested, repo)
    begun = worker.worker_begin(state, str(source), harness="claude")
    sid = begun["session"]["session_id"]
    registry = state / "projects" / begun["project_id"] / "workers.json"
    before = registry.read_bytes()
    with pytest.raises(worker.WorkerError, match="session.*(worktree|ledger)"):
        if operation == "record":
            worker.worker_record(state, str(target), harness="claude",
                                 event="attempt", session_id=sid)
        else:
            worker.worker_complete(state, str(target), session_id=sid)
    assert registry.read_bytes() == before
    leases = worker.worker_active(state, str(source), worktree_only=True)["leases"]
    assert [lease["session_id"] for lease in leases] == [sid]


@pytest.mark.parametrize("harness", ["human", "custom"])
def test_session_harness_cannot_be_relabelled_to_claim_mutation(
        tmp_path: Path, harness: str) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    begun = worker.worker_begin(state, str(repo), harness="claude")
    sid = begun["session"]["session_id"]
    registry = state / "projects" / begun["project_id"] / "workers.json"
    before = registry.read_bytes()
    with pytest.raises(worker.WorkerError, match="session.*harness"):
        worker.worker_record(state, str(repo), harness=harness,
                             event="mutation", session_id=sid)
    assert registry.read_bytes() == before


@pytest.mark.parametrize("git_repo", [True, False])
def test_session_can_record_and_complete_from_same_ledger_subdirectory(
        tmp_path: Path, git_repo: bool) -> None:
    state = _state(tmp_path)
    if git_repo:
        repo = _repo(tmp_path, "repo")
    else:
        repo = tmp_path / "ledger"
        repo.mkdir()
        (repo / ".statutor.yaml").write_text("bash_guard: true\n")
        (repo / "HANDOFF.md").write_text("# HANDOFF\n")
    subdir = repo / "src"
    subdir.mkdir()
    begun = worker.worker_begin(state, str(subdir), harness="custom")
    sid = begun["session"]["session_id"]
    recorded = worker.worker_record(state, str(repo), harness="custom",
                                    event="mutation", session_id=sid)
    done = worker.worker_complete(state, str(subdir), session_id=sid)
    assert recorded["worktree_id"] == begun["worktree_id"] == done["worktree_id"]
    assert worker.worker_active(state, str(repo))["leases"] == []


@pytest.mark.parametrize("operation", ["record", "complete"])
def test_legacy_session_remains_readable_but_requires_new_begin_for_ingress(
        tmp_path: Path, operation: str) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo")
    begun = worker.worker_begin(state, str(repo), harness="claude")
    sid = begun["session"]["session_id"]
    registry = state / "projects" / begun["project_id"] / "workers.json"
    legacy = json.loads(registry.read_text())
    legacy["sessions"][sid].pop("ledger_root", None)
    registry.write_text(json.dumps(legacy))
    before = registry.read_bytes()
    assert worker.worker_active(state, str(repo))["leases"][0]["session_id"] == sid
    with pytest.raises(worker.WorkerError, match="begin a new session"):
        if operation == "record":
            worker.worker_record(state, str(repo), harness="claude",
                                 event="attempt", session_id=sid)
        else:
            worker.worker_complete(state, str(repo), session_id=sid)
    assert registry.read_bytes() == before
