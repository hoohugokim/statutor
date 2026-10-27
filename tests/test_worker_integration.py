"""T-0041: crashes, reconciliation, capability reporting, isolated CLI E2E."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import statutor_worker as worker

TODAY = date.today().isoformat()


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _handoff(block: str) -> str:
    return (
        "# HANDOFF\n\n"
        f"last_verified: {TODAY} by `pytest`\n"
        f"{block}\n"
        "## Goal\ntest\n\n"
        "## Last verified state\ntest\n\n"
        "## Next action\ntest\n\n"
        "## Gotchas\nnone\n\n"
        "## Do not touch\nnone\n"
    )


ATTRIBUTED = ("last_worker: claude\nlast_machine: {mid}\n"
              "handoff_id: {hid}\nsupersedes: {sup}\n")


def _repo(tmp_path: Path, name: str, block: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / ".statutor.yaml").write_text("bash_guard: true\n")
    (root / "HANDOFF.md").write_text(_handoff(block))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    return root


def _state(tmp_path: Path, name: str = "state") -> Path:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    return root


def _expire(state: Path, cwd: str, session_id: str) -> None:
    project_id, _, _ = worker._resolve_project(cwd)
    path = worker._registry_path(state, project_id)
    registry = json.loads(path.read_text())
    registry["sessions"][session_id]["expires_at"] = "2000-01-01T00:00:00+00:00"
    for wt in registry["worktrees"].values():
        for lease in wt["leases"]:
            if lease["session_id"] == session_id:
                lease["expires_at"] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(registry))


# --------------------------------------------------------------------------
# first completion from an attributed baseline (no prior local completion)
# --------------------------------------------------------------------------

def test_first_completion_from_attributed_baseline(tmp_path: Path) -> None:
    state = _state(tmp_path)
    machine, _ = worker.ensure_machine(state)
    mid = machine["machine_id"]
    repo = _repo(tmp_path, "repo", ATTRIBUTED.format(
        mid=mid, hid="h0", sup="none"))
    begun = worker.worker_begin(state, str(repo), harness="claude")
    assert begun["session"]["baseline_handoff_id"] == "h0"
    (repo / "HANDOFF.md").write_text(_handoff(ATTRIBUTED.format(
        mid=mid, hid="h1", sup="h0")))
    done = worker.worker_complete(state, str(repo),
                                  session_id=begun["session"]["session_id"])
    assert done["record"]["handoff_id"] == "h1"
    assert done["reconciled"] is None


@pytest.mark.parametrize("legacy", [False, True])
def test_completion_retry_preserves_record_and_registry(
        tmp_path: Path, legacy: bool) -> None:
    state = _state(tmp_path)
    machine, _ = worker.ensure_machine(state)
    block = "" if legacy else ATTRIBUTED.format(
        mid=machine["machine_id"], hid="h0", sup="none")
    repo = _repo(tmp_path, "repo", block)
    begun = worker.worker_begin(state, str(repo), harness="claude")
    sid = begun["session"]["session_id"]
    if not legacy:
        (repo / "HANDOFF.md").write_text(_handoff(ATTRIBUTED.format(
            mid=machine["machine_id"], hid="h1", sup="h0")))
    done = worker.worker_complete(state, str(repo), session_id=sid)
    registry = worker._registry_path(state, begun["project_id"])
    before = registry.read_bytes()
    with pytest.raises(worker.WorkerError, match="session already completed") as error:
        worker.worker_complete(state, str(repo), session_id=sid)
    assert "worker show --basis completed" in str(error.value)
    assert "reconcile" not in str(error.value)
    assert registry.read_bytes() == before
    assert worker.worker_show(state, str(repo))["record"] == done["record"]
    assert worker.worker_active(state, str(repo))["leases"] == []


@pytest.mark.parametrize("change", ["body", "id", "machine"])
def test_completed_session_cannot_claim_changed_handoff(
        tmp_path: Path, change: str) -> None:
    state = _state(tmp_path)
    machine, _ = worker.ensure_machine(state)
    repo = _repo(tmp_path, "repo", ATTRIBUTED.format(
        mid=machine["machine_id"], hid="h0", sup="none"))
    begun = worker.worker_begin(state, str(repo), harness="claude")
    sid = begun["session"]["session_id"]
    path = repo / "HANDOFF.md"
    path.write_text(_handoff(ATTRIBUTED.format(
        mid=machine["machine_id"], hid="h1", sup="h0")))
    worker.worker_complete(state, str(repo), session_id=sid)
    if change == "machine":
        worker.rotate_machine(state, confirm=True)
    else:
        text = path.read_text()
        path.write_text(text + "changed\n" if change == "body"
                        else text.replace("handoff_id: h1", "handoff_id: h2"))
    registry = worker._registry_path(state, begun["project_id"])
    before = registry.read_bytes()
    with pytest.raises(worker.WorkerError, match="already completed"):
        worker.worker_complete(state, str(repo), session_id=sid)
    assert registry.read_bytes() == before


# --------------------------------------------------------------------------
# same-machine sibling reconciliation
# --------------------------------------------------------------------------

def _two_sessions_from_h0(tmp_path: Path):
    state = _state(tmp_path)
    machine, _ = worker.ensure_machine(state)
    mid = machine["machine_id"]
    repo = _repo(tmp_path, "repo", ATTRIBUTED.format(
        mid=mid, hid="h0", sup="none"))
    first = worker.worker_begin(state, str(repo), harness="claude")
    second = worker.worker_begin(state, str(repo), harness="claude")
    (repo / "HANDOFF.md").write_text(_handoff(ATTRIBUTED.format(
        mid=mid, hid="hA", sup="h0")))
    worker.worker_complete(state, str(repo),
                           session_id=first["session"]["session_id"])
    return state, repo, mid, second["session"]["session_id"]


def test_reconciliation_absorbing_sibling_completes(tmp_path: Path) -> None:
    state, repo, mid, sid = _two_sessions_from_h0(tmp_path)
    (repo / "HANDOFF.md").write_text(_handoff(ATTRIBUTED.format(
        mid=mid, hid="hC", sup="hA, h0")))
    done = worker.worker_complete(state, str(repo), session_id=sid)
    assert done["record"]["handoff_id"] == "hC"
    assert set(done["reconciled"]) == {"h0", "hA"}
    path = worker._registry_path(state, done["project_id"])
    before = path.read_bytes()
    with pytest.raises(worker.WorkerError, match="session already completed"):
        worker.worker_complete(state, str(repo), session_id=sid)
    assert path.read_bytes() == before
    assert worker.worker_show(state, str(repo))["record"] == done["record"]


def test_reconciliation_ignoring_sibling_rejected(tmp_path: Path) -> None:
    state, repo, mid, sid = _two_sessions_from_h0(tmp_path)
    (repo / "HANDOFF.md").write_text(_handoff(ATTRIBUTED.format(
        mid=mid, hid="hB", sup="h0")))
    with pytest.raises(worker.WorkerError, match="another local session"):
        worker.worker_complete(state, str(repo), session_id=sid)


def test_old_completion_retry_cannot_replace_newer_local_completion(
        tmp_path: Path) -> None:
    state = _state(tmp_path)
    machine, _ = worker.ensure_machine(state)
    repo = _repo(tmp_path, "repo", ATTRIBUTED.format(
        mid=machine["machine_id"], hid="h0", sup="none"))
    first = worker.worker_begin(state, str(repo), harness="claude")
    path = repo / "HANDOFF.md"
    first_text = _handoff(ATTRIBUTED.format(
        mid=machine["machine_id"], hid="hA", sup="h0"))
    path.write_text(first_text)
    worker.worker_complete(state, str(repo),
                           session_id=first["session"]["session_id"])
    second = worker.worker_begin(state, str(repo), harness="claude")
    path.write_text(_handoff(ATTRIBUTED.format(
        mid=machine["machine_id"], hid="hB", sup="hA")))
    latest = worker.worker_complete(state, str(repo),
                                    session_id=second["session"]["session_id"])
    path.write_text(first_text)
    registry = worker._registry_path(state, first["project_id"])
    before = registry.read_bytes()
    with pytest.raises(worker.WorkerError, match="already completed"):
        worker.worker_complete(state, str(repo),
                               session_id=first["session"]["session_id"])
    assert registry.read_bytes() == before
    assert worker.worker_show(state, str(repo))["record"] == latest["record"]


# --------------------------------------------------------------------------
# crashes: expiry never labels completion; newcomers proceed
# --------------------------------------------------------------------------

def test_crashed_session_ages_out_uncompleted(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo", _handoff(
        "last_worker: unknown\nlast_machine: unknown\n"
        "handoff_id: none\nsupersedes: none\n"))
    begun = worker.worker_begin(state, str(repo), harness="codex")
    sid = begun["session"]["session_id"]
    _expire(state, str(repo), sid)
    assert worker.worker_active(state, str(repo))["leases"] == []
    shown = worker.worker_show(state, str(repo), basis="completed")
    assert shown["record"] is None
    # A newcomer is unblocked: no local completion exists to collide with.
    next_up = worker.worker_begin(state, str(repo), harness="codex")
    done = worker.worker_complete(state, str(repo),
                                  session_id=next_up["session"]["session_id"])
    assert done["record"]["evidence"] == "completed"


def test_expired_session_may_still_complete_explicitly(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo", _handoff(
        "last_worker: unknown\nlast_machine: unknown\n"
        "handoff_id: none\nsupersedes: none\n"))
    begun = worker.worker_begin(state, str(repo), harness="human")
    sid = begun["session"]["session_id"]
    _expire(state, str(repo), sid)
    done = worker.worker_complete(state, str(repo), session_id=sid)
    assert done["record"]["session_id"] == sid


# --------------------------------------------------------------------------
# capability reporting
# --------------------------------------------------------------------------

def test_capabilities_pin_surfaces_and_gaps() -> None:
    caps = worker.all_capabilities()
    assert set(caps["capabilities"]) == set(worker.HARNESSES)
    for auto in ("claude", "codex", "opencode", "grok", "cursor"):
        entry = caps["capabilities"][auto]
        assert entry["proves_mutation"] is False
        assert entry["proves_completion"] is False
        assert entry["role_signal"] is False
        assert entry["verified_against"]
    assert caps["capabilities"]["custom"]["proves_mutation"] is True
    assert caps["capabilities"]["unknown"]["proves"] == ["activity"]
    begun_caps = worker.host_capabilities("codex")
    assert begun_caps["harness"] == "codex"


def test_begin_carries_host_capabilities(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo", _handoff(
        "last_worker: unknown\nlast_machine: unknown\n"
        "handoff_id: none\nsupersedes: none\n"))
    begun = worker.worker_begin(state, str(repo), harness="opencode")
    assert begun["capabilities"]["harness"] == "opencode"
    assert begun["capabilities"]["proves_mutation"] is False


# --------------------------------------------------------------------------
# isolated CLI end-to-end (no hosts, fake state root, tmp repo)
# --------------------------------------------------------------------------

def _cli(argv: list[str], capsys: pytest.CaptureFixture) -> tuple[int, object]:
    if argv[0] == "machine":
        code = worker.machine_cli(argv[1:])
    else:
        code = worker.worker_cli(argv[1:])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else None


def test_cli_end_to_end_attempt_to_completion(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo", _handoff(
        "last_worker: unknown\nlast_machine: unknown\n"
        "handoff_id: none\nsupersedes: none\n"))
    root_args = ["--state-root", str(state)]
    cwd_args = ["--cwd", str(repo)]

    code, shown = _cli(["machine", "show", *root_args, "--json"], capsys)
    assert code == 0
    mid = shown["machine"]["machine_id"]

    code, begun = _cli(["worker", "begin", *root_args, *cwd_args,
                        "--harness", "claude", "--json"], capsys)
    assert code == 0
    sid = begun["session"]["session_id"]

    code, _ = _cli(["worker", "record", *root_args, *cwd_args,
                    "--harness", "claude", "--event", "attempt",
                    "--session", sid, "--json"], capsys)
    assert code == 0

    code, _ = _cli(["worker", "record", *root_args, *cwd_args,
                    "--harness", "claude", "--event", "mutation",
                    "--session", sid, "--json"], capsys)
    assert code == 1  # automatic harnesses never prove mutation

    code, active = _cli(["worker", "active", *root_args, *cwd_args,
                         "--json"], capsys)
    assert code == 0 and len(active["leases"]) == 1

    (repo / "HANDOFF.md").write_text(_handoff(ATTRIBUTED.format(
        mid=mid, hid="h1", sup="none")))
    code, done = _cli(["worker", "complete", *root_args, *cwd_args,
                       "--session", sid, "--json"], capsys)
    assert code == 0
    assert done["record"]["handoff_id"] == "h1"

    code, shown = _cli(["worker", "show", *root_args, *cwd_args,
                        "--json"], capsys)
    assert code == 0
    assert shown["record"]["session_id"] == sid

    code, caps = _cli(["worker", "capabilities", *root_args, "--json"],
                      capsys)
    assert code == 0 and "claude" in caps["capabilities"]


def test_cli_record_outside_ledger_denied(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    state = _state(tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    code = worker.worker_cli(["record", "--state-root", str(state),
                              "--cwd", str(plain), "--harness", "claude",
                              "--event", "attempt", "--json"])
    capsys.readouterr()
    assert code == 1


@pytest.mark.parametrize("mode", ["machine", "worker"])
@pytest.mark.parametrize("position", ["before", "after", "override"])
def test_cli_root_options_reach_resolver(
        tmp_path: Path, capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch, mode: str, position: str) -> None:
    expected = {name: str(tmp_path / name)
                for name in ("home", "config_root", "state_root")}
    seen = []
    resolve = worker.substrate.resolve_roots

    def capture(**kwargs):
        seen.append(kwargs)
        return resolve(**kwargs)

    monkeypatch.setattr(worker.substrate, "resolve_roots", capture)
    monkeypatch.setenv("HOME", str(tmp_path / "fallback-home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "fallback-config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "fallback-state"))
    options = [item for name, value in expected.items()
               for item in ("--" + name.replace("_", "-"), value)]
    command = "show" if mode == "machine" else "capabilities"
    if position == "before":
        argv = [mode, *options, command, "--json"]
    elif position == "after":
        argv = [mode, command, *options, "--json"]
    else:
        parent_options = [item for name in expected
                          for item in ("--" + name.replace("_", "-"),
                                       str(tmp_path / ("parent-" + name)))]
        argv = [mode, *parent_options, command, *options, "--json"]
    assert _cli(argv, capsys)[0] == 0
    assert seen[-1] == expected


@pytest.mark.parametrize("position", ["before", "after"])
def test_cli_state_root_contains_entire_worker_flow_and_rotation(
        tmp_path: Path, capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch, position: str) -> None:
    state = _state(tmp_path, "explicit-state")
    fallback = tmp_path / "fallback-state"
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "fake-config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(fallback))
    repo = _repo(tmp_path, "repo", "")

    def run(mode, command, *options):
        roots = ["--state-root", str(state)]
        argv = ([mode, *roots, command] if position == "before"
                else [mode, command, *roots])
        code, result = _cli([*argv, *options, "--json"], capsys)
        assert code == 0
        return result

    machine = run("machine", "show")["machine"]
    assert (state / "machine.json").is_file()
    run("machine", "set-label", "explicit-only")
    begun = run("worker", "begin", "--harness", "human", "--cwd", str(repo))
    sid = begun["session"]["session_id"]
    run("worker", "record", "--harness", "human", "--event", "activity",
        "--session", sid, "--cwd", str(repo))
    assert run("worker", "active", "--cwd", str(repo))["leases"]
    completed = run("worker", "complete", "--session", sid, "--cwd", str(repo))
    roots = ["--state-root", str(state)]
    retry = (["worker", *roots, "complete"] if position == "before"
             else ["worker", "complete", *roots])
    code, _ = _cli([*retry, "--session", sid, "--cwd", str(repo), "--json"], capsys)
    assert code == 1
    assert run("worker", "show", "--cwd", str(repo))["record"] == completed["record"]
    run("worker", "compare", "HEAD", "--cwd", str(repo))
    run("worker", "capabilities")
    run("worker", "new-id")
    rotated = run("machine", "rotate", "--confirm")
    assert rotated["previous_machine_id"] == machine["machine_id"]
    assert rotated["machine"]["machine_id"] != machine["machine_id"]
    assert json.loads((state / "machine.json").read_text())["machine_id"] == \
        rotated["machine"]["machine_id"]
    assert not (fallback / "statutor").exists()


# --------------------------------------------------------------------------
# two fake machines, one git history (plan acceptance: pulled HANDOFF names
# the remote completing machine without importing its local state)
# --------------------------------------------------------------------------

def test_two_machines_share_history_without_importing_state(
        tmp_path: Path) -> None:
    state_a = _state(tmp_path, "state-a")
    state_b = _state(tmp_path, "state-b")
    machine_a, _ = worker.ensure_machine(state_a)
    machine_b, _ = worker.ensure_machine(state_b)
    assert machine_a["machine_id"] != machine_b["machine_id"]
    repo = _repo(tmp_path, "repo", _handoff(
        "last_worker: unknown\nlast_machine: unknown\n"
        "handoff_id: none\nsupersedes: none\n"))

    begun_a = worker.worker_begin(state_a, str(repo), harness="claude")
    (repo / "HANDOFF.md").write_text(_handoff(ATTRIBUTED.format(
        mid=machine_a["machine_id"], hid="hA", sup="none")))
    worker.worker_complete(state_a, str(repo),
                           session_id=begun_a["session"]["session_id"])

    # Machine B sees the same history: the pulled HANDOFF names A, but B's
    # local registry holds none of A's activity.
    assert worker.parse_handoff_fields(
        (repo / "HANDOFF.md").read_text())["last_machine"] == \
        machine_a["machine_id"]
    begun_b = worker.worker_begin(state_b, str(repo), harness="codex")
    assert begun_b["session"]["baseline_handoff_id"] == "hA"
    assert worker.worker_show(
        state_b, str(repo), basis="completed")["record"] is None
    (repo / "HANDOFF.md").write_text(_handoff(ATTRIBUTED.format(
        mid=machine_b["machine_id"], hid="hB", sup="hA").replace(
        "last_worker: claude", "last_worker: codex")))
    done_b = worker.worker_complete(state_b, str(repo),
                                    session_id=begun_b["session"]["session_id"])
    assert done_b["record"]["machine_id"] == machine_b["machine_id"]
    project_id, _, _ = worker._resolve_project(str(repo))
    registry_b = worker._registry_path(state_b, project_id).read_text()
    assert machine_a["machine_id"] not in registry_b
    registry_a = worker._registry_path(state_a, project_id).read_text()
    assert machine_b["machine_id"] not in registry_a


# --------------------------------------------------------------------------
# lock contention: busy path is deterministic, never corrupts
# --------------------------------------------------------------------------

def test_project_lock_busy_path(tmp_path: Path) -> None:
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo", _handoff(
        "last_worker: unknown\nlast_machine: unknown\n"
        "handoff_id: none\nsupersedes: none\n"))
    project_id, derivation, display = worker._resolve_project(str(repo))
    directory = worker._project_dir(state, project_id)
    with worker._ProjectLock(directory):
        with pytest.raises(worker.WorkerError, match="busy"):
            with worker._ProjectLock(directory):
                pass  # pragma: no cover
        with pytest.raises(worker.WorkerError, match="busy"):
            worker.worker_begin(state, str(repo), harness="claude")
    begun = worker.worker_begin(state, str(repo), harness="claude")
    assert begun["session"]["status"] == "active"


def test_held_lock_blocks_then_releases_across_threads(
        tmp_path: Path) -> None:
    import threading
    state = _state(tmp_path)
    repo = _repo(tmp_path, "repo", _handoff(
        "last_worker: unknown\nlast_machine: unknown\n"
        "handoff_id: none\nsupersedes: none\n"))
    project_id, _, _ = worker._resolve_project(str(repo))
    directory = worker._project_dir(state, project_id)
    entered = threading.Event()
    release = threading.Event()
    outcomes: list[str] = []

    def holder() -> None:
        with worker._ProjectLock(directory):
            entered.set()
            assert release.wait(timeout=30)
        worker.worker_begin(state, str(repo), harness="human")

    thread = threading.Thread(target=holder)
    thread.start()
    assert entered.wait(timeout=30)
    try:
        worker.worker_begin(state, str(repo), harness="claude")
        outcomes.append("unexpected-success")
    except worker.WorkerError as exc:
        outcomes.append("busy" if "busy" in str(exc) else f"other: {exc}")
    finally:
        release.set()
    thread.join(timeout=30)
    assert outcomes == ["busy"]
    registry = worker.validate_registry(worker.substrate.load_json(
        worker._registry_path(state, project_id)))
    assert len(registry["sessions"]) == 1
