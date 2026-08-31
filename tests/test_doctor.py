"""Tests for core/statutor_doctor.py — policy-derived budgets/sections (T-0009).

No conftest.py: each test module bootstraps its own sys.path so `core/` is
importable whether or not the package is installed.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import pytest

import statutor_core
import statutor_doctor

# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------

_STATUTOR_YAML_SOFT_MAX_5 = """\
bash_guard: true
governed:
  - pattern: AGENTS.md
    policy: constitution
    hard_max_lines: 200
    soft_max_lines: 5
  - pattern: HANDOFF.md
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

_STATUTOR_YAML_STALE_30 = """\
bash_guard: true
governed:
  - pattern: AGENTS.md
    policy: constitution
    hard_max_lines: 200
  - pattern: HANDOFF.md
    policy: overwrite_bounded
    max_lines: 40
    stale_after_days: 30
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


def _policy_soft_max_5() -> dict:
    """Dict equivalent of _STATUTOR_YAML_SOFT_MAX_5, for the sys.modules yaml
    stub — exercises the same override without needing real PyYAML."""
    return {
        "bash_guard": True,
        "governed": [
            {"pattern": "AGENTS.md", "policy": "constitution", "hard_max_lines": 200,
             "soft_max_lines": 5},
            {"pattern": "HANDOFF.md", "policy": "overwrite_bounded", "max_lines": 40,
             "required_sections": ["## Goal", "## Last verified state", "## Next action",
                                    "## Gotchas", "## Do not touch"]},
            {"pattern": "DECISIONS.md", "policy": "append_only"},
            {"pattern": "TASKS.md", "policy": "state"},
            {"pattern": "plans/archive/*", "policy": "frozen"},
        ],
    }


def _policy_stale_30() -> dict:
    """Dict equivalent of _STATUTOR_YAML_STALE_30, for the sys.modules yaml stub."""
    return {
        "bash_guard": True,
        "governed": [
            {"pattern": "AGENTS.md", "policy": "constitution", "hard_max_lines": 200},
            {"pattern": "HANDOFF.md", "policy": "overwrite_bounded", "max_lines": 40,
             "stale_after_days": 30,
             "required_sections": ["## Goal", "## Last verified state", "## Next action",
                                    "## Gotchas", "## Do not touch"]},
            {"pattern": "DECISIONS.md", "policy": "append_only"},
            {"pattern": "TASKS.md", "policy": "state"},
            {"pattern": "plans/archive/*", "policy": "frozen"},
        ],
    }


def _stub_yaml(monkeypatch: pytest.MonkeyPatch, policy: dict) -> None:
    """Inject a parsed policy for tests focused on doctor derivation."""
    monkeypatch.setattr(statutor_core, "load_worktree_policy", lambda root: policy)


def _handoff_text(last_verified: str) -> str:
    return (
        "<!-- statutor: plane=state -->\n"
        "# HANDOFF\n\n"
        f"last_verified: {last_verified} by `pytest`\n\n"
        "## Goal\ntest\n\n"
        "## Last verified state\ntest\n\n"
        "## Next action\ntest\n\n"
        "## Gotchas\nnone\n\n"
        "## Do not touch\nnone\n"
    )


def _base_files() -> dict[str, str]:
    return {
        "AGENTS.md": "# AGENTS\n\nShort constitution for tests.\n",
        "HANDOFF.md": _handoff_text(date.today().isoformat()),
        "DECISIONS.md": (
            "# DECISIONS\n\n"
            "## D-0001 — Example\n"
            "**Status:** accepted\n"
            "**Context:** x\n"
            "**Decision:** y\n"
            "**Consequences:** z\n"
        ),
        "TASKS.md": "# TASKS\n\n- [ ] T-0001 example task\n",
    }


def _write_ledger(root: Path, overrides: dict[str, str] | None = None,
                   omit: set[str] | None = None) -> None:
    files = _base_files()
    if overrides:
        files.update(overrides)
    for name, content in files.items():
        if omit and name in omit:
            continue
        (root / name).write_text(content, encoding="utf-8")


def _write_statutor_yaml(root: Path, text: str) -> None:
    (root / ".statutor.yaml").write_text(text, encoding="utf-8")


def run_doctor(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
               root: Path) -> tuple[str, int]:
    monkeypatch.setattr(sys, "argv", ["statutor-doctor", str(root)])
    with pytest.raises(SystemExit) as exc_info:
        statutor_doctor.main()
    out = capsys.readouterr().out
    return out, exc_info.value.code


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------

def test_clean_ledger_ok(tmp_path, monkeypatch, capsys):
    _write_ledger(tmp_path)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "OK    ledger clean." in out
    assert "WARN" not in out
    assert "ERROR" not in out


def test_missing_governed_file_errors(tmp_path, monkeypatch, capsys):
    _write_ledger(tmp_path, omit={"TASKS.md"})
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "ERROR missing governed file: TASKS.md" in out


@pytest.mark.parametrize("tasks,fragment", [
    ("- [ ] T-0001 one\n- [x] T-0001 duplicate\n", "duplicate state task ID T-0001"),
    ("- [maybe] T-0001 malformed\n", "state line 1 must be"),
])
def test_invalid_state_entries_error(tmp_path, monkeypatch, capsys, tasks, fragment):
    _write_ledger(tmp_path, overrides={"TASKS.md": tasks})
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert fragment in out


def test_agents_over_soft_budget_warns(tmp_path, monkeypatch, capsys):
    long_agents = "# AGENTS\n" + "line\n" * 130  # 131 lines > default 120
    _write_ledger(tmp_path, overrides={"AGENTS.md": long_agents})
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "WARN  AGENTS.md is 131 lines (soft budget 120)" in out


def test_custom_soft_max_lines_honored(tmp_path, monkeypatch, capsys):
    over_custom_agents = "# AGENTS\n" + "line\n" * 9  # 10 lines: over 5, under 120
    _write_ledger(tmp_path, overrides={"AGENTS.md": over_custom_agents})
    _write_statutor_yaml(tmp_path, _STATUTOR_YAML_SOFT_MAX_5)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "soft budget 5" in out


def test_custom_soft_max_lines_honored_stub_yaml(tmp_path, monkeypatch, capsys):
    """Same guarantee as the test above, via the sys.modules yaml stub, so
    it runs (and can actually kill a regression) regardless of whether
    PyYAML happens to be installed on the interpreter running pytest."""
    over_custom_agents = "# AGENTS\n" + "line\n" * 9  # 10 lines: over 5, under 120
    _write_ledger(tmp_path, overrides={"AGENTS.md": over_custom_agents})
    (tmp_path / ".statutor.yaml").write_text("placeholder: true\n", encoding="utf-8")
    _stub_yaml(monkeypatch, _policy_soft_max_5())
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "soft budget 5" in out


def test_stale_last_verified_warns(tmp_path, monkeypatch, capsys):
    stale_date = (date.today() - timedelta(days=10)).isoformat()
    _write_ledger(tmp_path, overrides={"HANDOFF.md": _handoff_text(stale_date)})
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "last verified 10 days ago" in out


def test_custom_stale_after_days_honored(tmp_path, monkeypatch, capsys):
    ten_days_ago = (date.today() - timedelta(days=10)).isoformat()
    _write_ledger(tmp_path, overrides={"HANDOFF.md": _handoff_text(ten_days_ago)})
    _write_statutor_yaml(tmp_path, _STATUTOR_YAML_STALE_30)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "OK    ledger clean." in out
    assert "last verified" not in out


def test_custom_stale_after_days_honored_stub_yaml(tmp_path, monkeypatch, capsys):
    """Same guarantee as the test above, via the sys.modules yaml stub —
    runs regardless of whether PyYAML is actually installed."""
    ten_days_ago = (date.today() - timedelta(days=10)).isoformat()
    _write_ledger(tmp_path, overrides={"HANDOFF.md": _handoff_text(ten_days_ago)})
    (tmp_path / ".statutor.yaml").write_text("placeholder: true\n", encoding="utf-8")
    _stub_yaml(monkeypatch, _policy_stale_30())
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "OK    ledger clean." in out
    assert "last verified" not in out


def test_missing_last_verified_stamp_errors(tmp_path, monkeypatch, capsys):
    no_stamp_handoff = (
        "# HANDOFF\n\n"
        "## Goal\ntest\n\n"
        "## Last verified state\ntest\n\n"
        "## Next action\ntest\n\n"
        "## Gotchas\nnone\n\n"
        "## Do not touch\nnone\n"
    )
    _write_ledger(tmp_path, overrides={"HANDOFF.md": no_stamp_handoff})
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "ERROR HANDOFF.md has no `last_verified: YYYY-MM-DD` stamp." in out


def test_invalid_date_is_reported_without_hiding_other_drift(tmp_path, monkeypatch, capsys):
    broken = _handoff_text("2026-02-31").replace("## Gotchas\nnone\n\n", "")
    _write_ledger(tmp_path, overrides={"HANDOFF.md": broken}, omit={"TASKS.md"})
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "invalid last_verified date 2026-02-31" in out
    assert "missing governed file: TASKS.md" in out
    assert "missing required sections: ## Gotchas" in out


def test_future_last_verified_date_is_error(tmp_path, monkeypatch, capsys):
    future = (date.today() + timedelta(days=10)).isoformat()
    _write_ledger(tmp_path, overrides={"HANDOFF.md": _handoff_text(future)})
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert f"last_verified date {future} is in the future" in out


def test_doctor_resolves_nearest_ledger_root_from_nested_directory(
        tmp_path, monkeypatch, capsys):
    _write_ledger(tmp_path)
    _write_statutor_yaml(tmp_path, statutor_core.TEMPLATES[".statutor.yaml"])
    nested = tmp_path / "src" / "deep"
    nested.mkdir(parents=True)
    out, code = run_doctor(monkeypatch, capsys, nested)
    assert code == 0
    assert "OK    ledger clean." in out


def test_missing_file_guidance_uses_current_cli(tmp_path, monkeypatch, capsys):
    _write_ledger(tmp_path, omit={"TASKS.md"})
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "run `statutor init .`" in out
    assert "/ledger-init" not in out


def test_consumed_plan_left_in_plans_warns(tmp_path, monkeypatch, capsys):
    _write_ledger(tmp_path, overrides={"TASKS.md": "# TASKS\n\n- [x] T-0001 done task\n"})
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    (plans_dir / "old-plan.md").write_text("Implements T-0001.\n", encoding="utf-8")
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "plans/old-plan.md references completed task(s)" in out
    assert "T-0001" in out


def test_consumed_plan_left_in_plans_warns_uppercase_checkbox(tmp_path, monkeypatch, capsys):
    """The consumed-plan heuristic matches `- [x]` case-insensitively
    (re.IGNORECASE); an uppercase `- [X]` (as some editors/agents write)
    must trigger the same warning."""
    _write_ledger(tmp_path, overrides={"TASKS.md": "# TASKS\n\n- [X] T-0001 done task\n"})
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    (plans_dir / "old-plan.md").write_text("Implements T-0001.\n", encoding="utf-8")
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "plans/old-plan.md references completed task(s)" in out
    assert "T-0001" in out


def test_missing_governed_file_list_is_policy_derived_not_hardcoded(tmp_path, monkeypatch, capsys):
    """The missing-file check list (statutor_doctor.check_names) must come from
    the repo's actual governed patterns, not a hardcoded four-name tuple:
    a policy governing RUNBOOK.md (and NOT TASKS.md) must error on a
    missing RUNBOOK.md and say nothing about the absent TASKS.md."""
    policy = {
        "bash_guard": True,
        "governed": [
            {"pattern": "AGENTS.md", "policy": "constitution", "hard_max_lines": 200},
            {"pattern": "HANDOFF.md", "policy": "overwrite_bounded", "max_lines": 40,
             "required_sections": ["## Goal", "## Last verified state", "## Next action",
                                    "## Gotchas", "## Do not touch"]},
            {"pattern": "DECISIONS.md", "policy": "append_only"},
            {"pattern": "RUNBOOK.md", "policy": "state"},
        ],
    }
    _write_ledger(tmp_path, omit={"TASKS.md"})
    (tmp_path / ".statutor.yaml").write_text("placeholder: true\n", encoding="utf-8")
    _stub_yaml(monkeypatch, policy)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "ERROR missing governed file: RUNBOOK.md" in out
    assert "TASKS.md" not in out


def test_decisions_missing_status_warns(tmp_path, monkeypatch, capsys):
    decisions = (
        "# DECISIONS\n\n"
        "## D-0001 — First\n"
        "**Status:** accepted\n"
        "**Context:** x\n"
        "**Decision:** y\n"
        "**Consequences:** z\n\n"
        "## D-0002 — Second\n"
        "**Context:** x\n"
        "**Decision:** y\n"
        "**Consequences:** z\n"
    )
    _write_ledger(tmp_path, overrides={"DECISIONS.md": decisions})
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "DECISIONS.md: 2 records but only 1 Status fields" in out


# --------------------------------------------------------------------------
# T-0009 gap 1: .statutor.yaml present but not applied (unappliable file)
# --------------------------------------------------------------------------

def test_no_statutor_yaml_present_produces_no_unapplied_warning(tmp_path, monkeypatch, capsys):
    """No .statutor.yaml at all is the normal embedded-defaults case — it must
    not be confused with the drift case of a present-but-unusable file."""
    _write_ledger(tmp_path)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "present but not applied" not in out


def test_statutor_yaml_applies_without_pyyaml(tmp_path, monkeypatch, capsys):
    _write_ledger(tmp_path)
    _write_statutor_yaml(tmp_path, _STATUTOR_YAML_SOFT_MAX_5)
    monkeypatch.setitem(sys.modules, "yaml", None)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "OK    ledger clean." in out
    assert "present but not applied" not in out


def test_pristine_scaffold_statutor_yaml_never_warns_without_pyyaml(tmp_path, monkeypatch, capsys):
    """A .statutor.yaml byte-identical to the scaffold template IS the
    embedded defaults, so the PyYAML-less fallback loses nothing — a fresh
    `statutor init` ledger must stay warning-free on every interpreter
    (regression: first CI run, pyyaml=false legs, 2026-08-24)."""
    _write_ledger(tmp_path)
    (tmp_path / ".statutor.yaml").write_text(
        statutor_core.TEMPLATES[".statutor.yaml"], encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "present but not applied" not in out


def test_statutor_yaml_missing_governed_is_error(tmp_path, monkeypatch, capsys):
    _write_ledger(tmp_path)
    (tmp_path / ".statutor.yaml").write_text("bash_guard: false\n", encoding="utf-8")
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "ERROR invalid .statutor.yaml" in out
    assert "missing governed list" in out


def test_statutor_yaml_present_and_applied_produces_no_unapplied_warning_stub_yaml(tmp_path, monkeypatch, capsys):
    """The converse of the two tests above: when load_policy actually
    applies the file (returns a distinct dict, not the DEFAULT_POLICY
    object), no 'not applied' warning should fire."""
    _write_ledger(tmp_path, overrides={"AGENTS.md": "# AGENTS\n" + "line\n" * 9})
    (tmp_path / ".statutor.yaml").write_text("placeholder: true\n", encoding="utf-8")
    _stub_yaml(monkeypatch, _policy_soft_max_5())
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "present but not applied" not in out


# --------------------------------------------------------------------------
# T-0009 gap 2: filenames derived from the matched rule's pattern
# --------------------------------------------------------------------------

def test_custom_constitution_filename_honored_stub_yaml(tmp_path, monkeypatch, capsys):
    """The soft-budget check must apply to whichever file the constitution
    rule actually governs (here RULES.md), not the literal AGENTS.md."""
    policy = {
        "bash_guard": True,
        "governed": [
            {"pattern": "RULES.md", "policy": "constitution", "hard_max_lines": 200,
             "soft_max_lines": 5},
            {"pattern": "HANDOFF.md", "policy": "overwrite_bounded", "max_lines": 40,
             "required_sections": ["## Goal", "## Last verified state", "## Next action",
                                    "## Gotchas", "## Do not touch"]},
            {"pattern": "DECISIONS.md", "policy": "append_only"},
            {"pattern": "TASKS.md", "policy": "state"},
        ],
    }
    _write_ledger(tmp_path, omit={"AGENTS.md"})
    (tmp_path / "RULES.md").write_text("# RULES\n" + "line\n" * 9, encoding="utf-8")  # 10 lines
    (tmp_path / ".statutor.yaml").write_text("placeholder: true\n", encoding="utf-8")
    _stub_yaml(monkeypatch, policy)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "RULES.md is 10 lines (soft budget 5)" in out
    assert "AGENTS.md" not in out


def test_custom_overwrite_bounded_filename_honored_for_staleness_stub_yaml(tmp_path, monkeypatch, capsys):
    """The staleness check must apply to whichever file the
    overwrite_bounded rule actually governs (here STATUS.md), not the
    literal HANDOFF.md."""
    policy = {
        "bash_guard": True,
        "governed": [
            {"pattern": "AGENTS.md", "policy": "constitution", "hard_max_lines": 200},
            {"pattern": "STATUS.md", "policy": "overwrite_bounded", "max_lines": 40,
             "required_sections": ["## Goal", "## Next action"]},
            {"pattern": "DECISIONS.md", "policy": "append_only"},
            {"pattern": "TASKS.md", "policy": "state"},
        ],
    }
    _write_ledger(tmp_path, omit={"HANDOFF.md"})
    stale_date = (date.today() - timedelta(days=10)).isoformat()
    status_text = (
        f"last_verified: {stale_date} by `pytest`\n\n"
        "## Goal\ntest\n\n"
        "## Next action\ntest\n"
    )
    (tmp_path / "STATUS.md").write_text(status_text, encoding="utf-8")
    (tmp_path / ".statutor.yaml").write_text("placeholder: true\n", encoding="utf-8")
    _stub_yaml(monkeypatch, policy)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "STATUS.md last verified 10 days ago" in out
    assert "HANDOFF.md" not in out


# --------------------------------------------------------------------------
# T-0009 gap 3: required_sections read from policy, ERROR on drift
# --------------------------------------------------------------------------

def test_handoff_missing_required_section_on_disk_errors(tmp_path, monkeypatch, capsys):
    """A HANDOFF.md that reached disk missing a mandated section means the
    hook/floor was bypassed — that's drift, and doctor must ERROR (staged
    mode already treats it as a violation; doctor previously never read
    required_sections at all)."""
    handoff_missing_gotchas = (
        f"last_verified: {date.today().isoformat()} by `pytest`\n\n"
        "## Goal\ntest\n\n"
        "## Last verified state\ntest\n\n"
        "## Next action\ntest\n\n"
        "## Do not touch\nnone\n"
    )
    _write_ledger(tmp_path, overrides={"HANDOFF.md": handoff_missing_gotchas})
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "ERROR HANDOFF.md is missing required sections: ## Gotchas" in out


def test_custom_overwrite_bounded_filename_missing_section_errors_stub_yaml(tmp_path, monkeypatch, capsys):
    """Same drift check as above, but on a custom overwrite_bounded
    filename (STATUS.md) — required_sections must be read from the matched
    rule regardless of which file it governs, and exit code must be 1."""
    policy = {
        "bash_guard": True,
        "governed": [
            {"pattern": "AGENTS.md", "policy": "constitution", "hard_max_lines": 200},
            {"pattern": "STATUS.md", "policy": "overwrite_bounded", "max_lines": 40,
             "required_sections": ["## Goal", "## Next action", "## Gotchas"]},
            {"pattern": "DECISIONS.md", "policy": "append_only"},
            {"pattern": "TASKS.md", "policy": "state"},
        ],
    }
    _write_ledger(tmp_path, omit={"HANDOFF.md"})
    status_text = (
        f"last_verified: {date.today().isoformat()} by `pytest`\n\n"
        "## Goal\ntest\n\n"
        "## Next action\ntest\n"
        # "## Gotchas" intentionally omitted
    )
    (tmp_path / "STATUS.md").write_text(status_text, encoding="utf-8")
    (tmp_path / ".statutor.yaml").write_text("placeholder: true\n", encoding="utf-8")
    _stub_yaml(monkeypatch, policy)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "STATUS.md is missing required sections: ## Gotchas" in out
    assert "HANDOFF.md" not in out


def test_all_required_sections_present_no_error(tmp_path, monkeypatch, capsys):
    """Sanity check: a compliant HANDOFF.md (all sections present) must not
    trip the new gap-3 check — guards against a too-eager implementation."""
    _write_ledger(tmp_path)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "missing required sections" not in out


# --------------------------------------------------------------------------
# T-0013: remaining hardcoded names derived from policy
# --------------------------------------------------------------------------

def test_custom_state_filename_drives_done_ids_and_plan_heuristic_stub_yaml(tmp_path, monkeypatch, capsys):
    """The consumed-plan heuristic must read done ids from whichever file the
    state rule governs (here BACKLOG.md), not the literal TASKS.md: with
    BACKLOG.md marking T-0001 done and TASKS.md leaving it open, the plan
    referencing T-0001 must still be flagged."""
    policy = {
        "bash_guard": True,
        "governed": [
            {"pattern": "AGENTS.md", "policy": "constitution", "hard_max_lines": 200},
            {"pattern": "HANDOFF.md", "policy": "overwrite_bounded", "max_lines": 40,
             "required_sections": ["## Goal", "## Last verified state", "## Next action",
                                    "## Gotchas", "## Do not touch"]},
            {"pattern": "DECISIONS.md", "policy": "append_only"},
            {"pattern": "BACKLOG.md", "policy": "state"},
        ],
    }
    _write_ledger(tmp_path, overrides={"TASKS.md": "- [ ] T-0001 open here\n"})
    (tmp_path / "BACKLOG.md").write_text("- [x] T-0001 done there\n", encoding="utf-8")
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir(exist_ok=True)
    (plans_dir / "old-plan.md").write_text("Implements T-0001.\n", encoding="utf-8")
    (tmp_path / ".statutor.yaml").write_text("placeholder: true\n", encoding="utf-8")
    _stub_yaml(monkeypatch, policy)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "plans/old-plan.md references completed task(s) ['T-0001']" in out


def test_custom_append_only_filename_status_check_stub_yaml(tmp_path, monkeypatch, capsys):
    """The D-record Status check must apply to whichever file the append_only
    rule governs (here CHOICES.md): a statusless CHOICES record warns by
    name, while a statusless DECISIONS.md record goes unflagged because no
    rule points at that filename anymore."""
    policy = {
        "bash_guard": True,
        "governed": [
            {"pattern": "AGENTS.md", "policy": "constitution", "hard_max_lines": 200},
            {"pattern": "HANDOFF.md", "policy": "overwrite_bounded", "max_lines": 40,
             "required_sections": ["## Goal", "## Last verified state", "## Next action",
                                    "## Gotchas", "## Do not touch"]},
            {"pattern": "CHOICES.md", "policy": "append_only"},
            {"pattern": "TASKS.md", "policy": "state"},
        ],
    }
    _write_ledger(tmp_path, overrides={
        "DECISIONS.md": "# DECISIONS\n\n## D-0001\nno status field\n"})
    (tmp_path / "CHOICES.md").write_text(
        "# CHOICES\n\n## D-0001 — Example\n**Context:** x\n**Decision:** y\n", encoding="utf-8")
    (tmp_path / ".statutor.yaml").write_text("placeholder: true\n", encoding="utf-8")
    _stub_yaml(monkeypatch, policy)
    out, code = run_doctor(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "CHOICES.md: 1 records but only 0 Status fields" in out
    assert "DECISIONS.md" not in out
