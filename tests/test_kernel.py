"""Tests for core/statutor_core.py — the statutor kernel (T-0001, porting the manual battery).

No conftest.py: this module bootstraps its own sys.path so `core/` is
importable whether or not the package is installed.

Where the informal manual battery and the actual kernel disagree, the
kernel wins: tests named *_quirk pin CURRENT behavior rather than the
behavior one might expect from the docs. Do not "fix" those tests without
also fixing (and consciously choosing to change) the kernel.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import pytest

import statutor_core

REPO_ROOT = Path(__file__).resolve().parents[1]
KERNEL = REPO_ROOT / "core" / "statutor_core.py"
POLICY = statutor_core.DEFAULT_POLICY  # pass explicitly; never mutate the returned dict

HANDOFF_RULE = next(r for r in POLICY["governed"] if r["pattern"] == "HANDOFF.md")
REQUIRED_SECTIONS: list[str] = HANDOFF_RULE["required_sections"]

NO_GIT = shutil.which("git") is None
git_required = pytest.mark.skipif(NO_GIT, reason="git not available")

GIT_ENV = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}

# --------------------------------------------------------------------------
# guard: isolate every git subprocess this suite spawns from the developer's
# real ~/.gitconfig, INCLUDING the ones statutor_core._git_bytes() spawns
# in-process. T-0025 no longer parses rendered diffs for append-only checks,
# but hermetic config still prevents user aliases/attributes from changing
# unrelated Git behavior and preserves the hostile-color regression.
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _isolate_git_config_for_whole_session():
    saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL")}
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# --------------------------------------------------------------------------
# guard: no test may mutate the shared DEFAULT_POLICY object (K-22)
# --------------------------------------------------------------------------

_DEFAULT_POLICY_SNAPSHOT = copy.deepcopy(statutor_core.DEFAULT_POLICY)


@pytest.fixture(autouse=True)
def _guard_default_policy():
    yield
    assert statutor_core.DEFAULT_POLICY == _DEFAULT_POLICY_SNAPSHOT


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def lines(n: int, trailing_newline: bool = False) -> str:
    """Exactly `n` physical lines, optionally terminated by LF."""
    content = "\n".join(f"x{i}" for i in range(n))
    return content + "\n" if trailing_newline else content


def handoff(drop: tuple[str, ...] = ()) -> str:
    """Compliant HANDOFF body, well under the 40-line cap."""
    body = ["# HANDOFF", ""]
    for s in REQUIRED_SECTIONS:
        if s in drop:
            continue
        body += [s, "x", ""]
    while body and body[-1] == "":
        body.pop()
    return "\n".join(body) + "\n"


def handoff_padded(total_lines: int, trailing_newline: bool = False) -> str:
    """Compliant HANDOFF body, padded with filler lines to exactly `total_lines`
    counted lines (content.count('\\n') + 1) before any trailing_newline is added."""
    body = ["# HANDOFF", ""]
    for s in REQUIRED_SECTIONS:
        body += [s, "x", ""]
    while body and body[-1] == "":
        body.pop()
    filler_needed = total_lines - len(body)
    assert filler_needed >= 0, f"total_lines too small: need at least {len(body)}"
    for i in range(filler_needed):
        body.append(f"filler{i}")
    content = "\n".join(body)
    assert content.count("\n") + 1 == total_lines
    if trailing_newline:
        content += "\n"
    return content


def run_kernel(args: list[str], cwd: str | None = None,
               input_str: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(KERNEL), *args], cwd=cwd,
                          input=input_str, capture_output=True, text=True)


def git(cwd, *args, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.email=statutor@test", "-c", "user.name=statutor test",
                            "-c", "commit.gpgsign=false", *args], cwd=str(cwd), env=GIT_ENV,
                           capture_output=True, text=True, check=check)


def commit_all(repo, message: str = "commit") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def ledger_repo(tmp_path):
    if NO_GIT:
        pytest.skip("git not available")
    repo = tmp_path
    git(repo, "init", "-q", "-b", "main")
    (repo / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001\nfirst\n", encoding="utf-8")
    (repo / "HANDOFF.md").write_text(handoff(), encoding="utf-8")
    (repo / "AGENTS.md").write_text("# AGENTS\n\nShort constitution.\n", encoding="utf-8")
    (repo / "TASKS.md").write_text("- [ ] T-0001 one\n- [ ] T-0002 two\n", encoding="utf-8")
    (repo / "plans").mkdir()
    (repo / "plans" / "p1.md").write_text("plan one\n", encoding="utf-8")
    (repo / "plans" / "archive").mkdir()
    (repo / "plans" / "archive" / "a1.md").write_text("archived one\n", encoding="utf-8")
    commit_all(repo, "init ledger")
    return repo


# --------------------------------------------------------------------------
# _norm (K-01..K-04)
# --------------------------------------------------------------------------

def test_norm_camelcase_maps_to_snake_case():
    out = statutor_core._norm({"filePath": "a", "oldString": "o", "newString": "n"})
    assert out["file_path"] == "a"
    assert out["old_string"] == "o"
    assert out["new_string"] == "n"
    assert out["filePath"] == "a"
    assert out["oldString"] == "o"
    assert out["newString"] == "n"


def test_norm_snake_case_wins_when_both_present():
    out = statutor_core._norm({"filePath": "a", "file_path": "b"})
    assert out["file_path"] == "b"


def test_norm_none_and_empty():
    assert statutor_core._norm(None) == {}
    assert statutor_core._norm({}) == {}


def test_norm_does_not_mutate_argument():
    src = {"filePath": "a"}
    statutor_core._norm(src)
    assert src == {"filePath": "a"}


# --------------------------------------------------------------------------
# _match_rule (K-05..K-12)
# --------------------------------------------------------------------------

def test_match_rule_exact_basename():
    rule = statutor_core._match_rule("DECISIONS.md", POLICY)
    assert rule["policy"] == "append_only"


def test_match_rule_basename_at_any_depth_quirk():
    rule = statutor_core._match_rule("docs/DECISIONS.md", POLICY)
    assert rule["policy"] == "append_only"


def test_match_rule_path_pattern():
    rule = statutor_core._match_rule("plans/archive/old.md", POLICY)
    assert rule["policy"] == "frozen"


def test_match_rule_glob_star_spans_slash_quirk():
    rule = statutor_core._match_rule("plans/archive/sub/deep.md", POLICY)
    assert rule["policy"] == "frozen"


@pytest.mark.parametrize("path", ["plans/archive", "plans/active.md", "src/main.py"])
def test_match_rule_non_governed_paths(path):
    assert statutor_core._match_rule(path, POLICY) is None


def test_match_rule_no_partial_name_matching():
    assert statutor_core._match_rule("AGENTS.md.bak", POLICY) is None


def test_match_rule_os_sep_normalized():
    rule = statutor_core._match_rule(os.path.join("plans", "archive", "x.md"), POLICY)
    assert rule["policy"] == "frozen"


def test_match_rule_outside_cwd_still_governed_quirk():
    rule = statutor_core._match_rule("../DECISIONS.md", POLICY)
    assert rule["policy"] == "append_only"


# --------------------------------------------------------------------------
# load_policy (K-13..K-22)
# --------------------------------------------------------------------------

def test_load_policy_no_statutor_yaml_returns_default_identity(tmp_path):
    assert statutor_core.load_policy(str(tmp_path)) is statutor_core.DEFAULT_POLICY


def test_load_policy_uses_committed_head_snapshot(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".statutor.yaml").write_text(
        "governed:\n  - pattern: TASKS.md\n    policy: append_only\n", encoding="utf-8")
    commit_all(tmp_path, "policy")
    policy = statutor_core.load_policy(str(tmp_path))
    assert policy["governed"] == [{"pattern": "TASKS.md", "policy": "append_only"}]
    assert policy["bash_guard"] is True


def test_load_policy_ignores_unstaged_worktree_policy(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".statutor.yaml").write_text(
        "governed:\n  - pattern: TASKS.md\n    policy: append_only\n", encoding="utf-8")
    commit_all(tmp_path, "policy")
    (tmp_path / ".statutor.yaml").write_text("governed: []\n", encoding="utf-8")
    policy = statutor_core.load_policy(str(tmp_path))
    assert policy["governed"] == [{"pattern": "TASKS.md", "policy": "append_only"}]


def test_parse_policy_needs_no_pyyaml(monkeypatch):
    monkeypatch.setitem(sys.modules, "yaml", None)
    policy = statutor_core.parse_policy(
        "bash_guard: false\ngoverned:\n"
        "  - pattern: TASKS.md\n    policy: append_only\n")
    assert policy == {"bash_guard": False, "governed": [
        {"pattern": "TASKS.md", "policy": "append_only"}]}


def test_parse_policy_malformed_yaml_is_error():
    with pytest.raises(statutor_core._PolicyFailure):
        statutor_core.parse_policy("::: not yaml [")


def test_parse_policy_mapping_without_governed_is_error():
    with pytest.raises(statutor_core._PolicyFailure, match="missing governed"):
        statutor_core.parse_policy("bash_guard: false\n")


def test_parse_policy_unknown_keys_are_error():
    with pytest.raises(statutor_core._PolicyFailure, match="unknown top-level"):
        statutor_core.parse_policy("placeholder: true\ngoverned: []\n")


def test_parse_policy_quoted_numeric_caps_normalized():
    policy = statutor_core.parse_policy(
        "governed:\n  - pattern: HANDOFF.md\n"
        "    policy: overwrite_bounded\n    max_lines: \"40\"\n")
    assert policy["governed"][0]["max_lines"] == 40


def test_load_policy_malformed_committed_policy_is_error(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".statutor.yaml").write_text("::: not yaml [\n", encoding="utf-8")
    commit_all(tmp_path, "bad policy")
    with pytest.raises(statutor_core._PolicyFailure):
        statutor_core.load_policy(str(tmp_path))


def test_load_policy_empty_governed_list_honored(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".statutor.yaml").write_text("governed: []\n", encoding="utf-8")
    commit_all(tmp_path, "empty policy")
    policy = statutor_core.load_policy(str(tmp_path))
    assert policy["governed"] == []
    assert statutor_core._match_rule("DECISIONS.md", policy) is None


# --------------------------------------------------------------------------
# validate/dispatch (K-23..K-28)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tool", ["write", "Write", "WRITE"])
def test_validate_tool_name_lowercased(tmp_path, tool):
    payload = {"file_path": str(tmp_path / "AGENTS.md"), "content": lines(201)}
    result = statutor_core.validate(tool, payload, str(tmp_path), POLICY)
    assert result is not None
    assert "hard cap 200" in result


def test_validate_normalizes_camelcase_payload(tmp_path):
    payload = {"filePath": str(tmp_path / "AGENTS.md"), "content": lines(201)}
    result = statutor_core.validate("write", payload, str(tmp_path), POLICY)
    assert result is not None


@pytest.mark.parametrize("tool", ["read", "grep", "glob"])
def test_validate_non_mutating_tools_pass(tmp_path, tool):
    payload = {"file_path": str(tmp_path / "DECISIONS.md")}
    assert statutor_core.validate(tool, payload, str(tmp_path), POLICY) is None


@pytest.mark.parametrize("tool,file_path", [
    ("multiedit", "DECISIONS.md"), ("notebookedit", "DECISIONS.md"),
    ("multiedit", "plans/archive/x.md"), ("notebookedit", "plans/archive/x.md"),
])
def test_validate_multiedit_notebookedit_uncovered_quirk(tmp_path, tool, file_path):
    payload = {"file_path": str(tmp_path / file_path)}
    assert statutor_core.validate(tool, payload, str(tmp_path), POLICY) is None


@pytest.mark.parametrize("tool", ["write", "edit"])
@pytest.mark.parametrize("payload", [{}, {"file_path": ""}])
def test_validate_empty_or_absent_file_path(tmp_path, tool, payload):
    assert statutor_core.validate(tool, payload, str(tmp_path), POLICY) is None


def test_validate_explicit_policy_bypasses_load_policy(tmp_path, monkeypatch):
    def _boom(cwd):
        raise AssertionError("load_policy should not be called")
    monkeypatch.setattr(statutor_core, "load_policy", _boom)
    payload = {"file_path": str(tmp_path / "AGENTS.md"), "content": "x"}
    assert statutor_core.validate("write", payload, str(tmp_path), policy=POLICY) is None


# --------------------------------------------------------------------------
# constitution (K-29..K-33)
# --------------------------------------------------------------------------

def test_constitution_over_cap_denied(tmp_path):
    payload = {"file_path": str(tmp_path / "AGENTS.md"), "content": lines(201)}
    result = statutor_core.validate("write", payload, str(tmp_path), POLICY)
    assert "would be 201 lines (hard cap 200)" in result


def test_constitution_exactly_at_cap_ok(tmp_path):
    payload = {"file_path": str(tmp_path / "AGENTS.md"), "content": lines(200)}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


def test_constitution_trailing_newline_does_not_invent_line(tmp_path):
    payload = {"file_path": str(tmp_path / "AGENTS.md"), "content": lines(200, trailing_newline=True)}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


def test_constitution_edit_result_over_cap_denied(tmp_path):
    (tmp_path / "AGENTS.md").write_text("x\n", encoding="utf-8")
    payload = {"file_path": str(tmp_path / "AGENTS.md"),
               "old_string": "x", "new_string": lines(300)}
    result = statutor_core.validate("edit", payload, str(tmp_path), POLICY)
    assert "would be 300 lines (hard cap 200)" in result


def test_constitution_custom_hard_max_lines_honored(tmp_path):
    policy = {"governed": [{"pattern": "AGENTS.md", "policy": "constitution", "hard_max_lines": 3}]}
    payload = {"file_path": str(tmp_path / "AGENTS.md"), "content": lines(4)}
    result = statutor_core.validate("write", payload, str(tmp_path), policy)
    assert "hard cap 3" in result


# --------------------------------------------------------------------------
# overwrite_bounded (K-34..K-42)
# --------------------------------------------------------------------------

def test_overwrite_bounded_over_cap_denied(tmp_path):
    content = handoff_padded(total_lines=52)
    payload = {"file_path": str(tmp_path / "HANDOFF.md"), "content": content}
    result = statutor_core.validate("write", payload, str(tmp_path), POLICY)
    assert "would be 52 lines (cap 40)" in result
    assert "shift-change note" in result


def test_overwrite_bounded_exactly_at_cap_ok(tmp_path):
    content = handoff_padded(total_lines=40)
    payload = {"file_path": str(tmp_path / "HANDOFF.md"), "content": content}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


def test_overwrite_bounded_trailing_newline_does_not_invent_line(tmp_path):
    content = handoff_padded(total_lines=40, trailing_newline=True)
    payload = {"file_path": str(tmp_path / "HANDOFF.md"), "content": content}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_overwrite_bounded_missing_one_section(tmp_path, section):
    payload = {"file_path": str(tmp_path / "HANDOFF.md"), "content": handoff(drop=(section,))}
    result = statutor_core.validate("write", payload, str(tmp_path), POLICY)
    assert "missing required sections:" in result
    assert section in result


def test_overwrite_bounded_missing_two_sections_comma_joined(tmp_path):
    drop = ("## Gotchas", "## Do not touch")
    payload = {"file_path": str(tmp_path / "HANDOFF.md"), "content": handoff(drop=drop)}
    result = statutor_core.validate("write", payload, str(tmp_path), POLICY)
    assert "## Gotchas, ## Do not touch" in result


def test_overwrite_bounded_cap_precedes_missing_sections(tmp_path):
    content = "\n".join(f"line{i}" for i in range(60))  # over cap, no sections at all
    payload = {"file_path": str(tmp_path / "HANDOFF.md"), "content": content}
    result = statutor_core.validate("write", payload, str(tmp_path), POLICY)
    assert "cap 40" in result
    assert "missing required sections" not in result


def test_overwrite_bounded_substring_heading_match_quirk(tmp_path):
    content = handoff().replace("## ", "### ")
    payload = {"file_path": str(tmp_path / "HANDOFF.md"), "content": content}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


def test_overwrite_bounded_inline_mention_satisfies_sections_quirk(tmp_path):
    content = "See " + ", ".join(REQUIRED_SECTIONS) + " for details.\n"
    payload = {"file_path": str(tmp_path / "HANDOFF.md"), "content": content}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


def test_overwrite_bounded_edit_result_over_cap_denied(tmp_path):
    (tmp_path / "HANDOFF.md").write_text("x\n", encoding="utf-8")
    payload = {"file_path": str(tmp_path / "HANDOFF.md"),
               "old_string": "x", "new_string": lines(300)}
    result = statutor_core.validate("edit", payload, str(tmp_path), POLICY)
    assert "would be 300 lines (cap 40)" in result


def test_overwrite_bounded_edit_rechecks_required_sections(tmp_path):
    original = handoff()
    (tmp_path / "HANDOFF.md").write_text(original, encoding="utf-8")
    payload = {"file_path": "HANDOFF.md", "old_string": "## Goal", "new_string": "## Aim"}
    result = statutor_core.validate("edit", payload, str(tmp_path), POLICY)
    assert "missing required sections: ## Goal" in result


def test_relative_tool_path_resolves_against_explicit_cwd(tmp_path):
    (tmp_path / "plans" / "archive").mkdir(parents=True)
    payload = {"file_path": "plans/archive/a.md", "content": "changed\n"}
    result = statutor_core.validate("write", payload, str(tmp_path), POLICY)
    assert "frozen" in result


def test_overwrite_bounded_custom_rule_honored(tmp_path):
    policy = {"governed": [{"pattern": "HANDOFF.md", "policy": "overwrite_bounded",
                             "max_lines": 2, "required_sections": ["## Only"]}]}
    over_cap = statutor_core.validate(
        "write", {"file_path": str(tmp_path / "HANDOFF.md"), "content": lines(3)},
        str(tmp_path), policy)
    assert "cap 2" in over_cap
    missing_section = statutor_core.validate(
        "write", {"file_path": str(tmp_path / "HANDOFF.md"), "content": "a"},
        str(tmp_path), policy)
    assert "## Only" in missing_section


# --------------------------------------------------------------------------
# append_only / edit (K-43..K-49)
# --------------------------------------------------------------------------

def _edit_decisions(tmp_path, old: str, new: str):
    payload = {"file_path": str(tmp_path / "DECISIONS.md"), "old_string": old, "new_string": new}
    return statutor_core.validate("edit", payload, str(tmp_path), POLICY)


def test_append_only_edit_pure_insertion_ok(tmp_path):
    assert _edit_decisions(tmp_path, "body", "body\nmore") is None


def test_append_only_edit_noop_ok(tmp_path):
    assert _edit_decisions(tmp_path, "body", "body") is None


def test_append_only_edit_empty_old_string_short_circuits(tmp_path):
    assert _edit_decisions(tmp_path, "", "anything") is None


def test_append_only_edit_defaults_to_empty_strings(tmp_path):
    payload = {"file_path": str(tmp_path / "DECISIONS.md")}
    assert statutor_core.validate("edit", payload, str(tmp_path), POLICY) is None


def test_append_only_edit_modification_denied(tmp_path):
    result = _edit_decisions(tmp_path, "body", "gone")
    assert "append-only" in result
    assert "new_string must contain old_string verbatim" in result


def test_append_only_edit_prepend_allowed_quirk(tmp_path):
    assert _edit_decisions(tmp_path, "body", "PRE\nbody") is None


def test_append_only_edit_deletion_denied(tmp_path):
    result = _edit_decisions(tmp_path, "body", "")
    assert result is not None
    assert "append-only" in result


# --------------------------------------------------------------------------
# append_only / write (K-50..K-55)
# --------------------------------------------------------------------------

def test_append_only_write_full_rewrite_containing_existing_ok(tmp_path):
    existing = "line1\nline2\n"
    (tmp_path / "DECISIONS.md").write_text(existing, encoding="utf-8")
    payload = {"file_path": str(tmp_path / "DECISIONS.md"), "content": existing + "line3\n"}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


def test_append_only_write_drops_content_denied(tmp_path):
    (tmp_path / "DECISIONS.md").write_text("line1\nline2\n", encoding="utf-8")
    payload = {"file_path": str(tmp_path / "DECISIONS.md"), "content": "line1\n"}
    result = statutor_core.validate("write", payload, str(tmp_path), POLICY)
    assert "A full rewrite must contain the existing content verbatim" in result


def test_append_only_write_missing_file_treated_as_empty(tmp_path):
    payload = {"file_path": str(tmp_path / "DECISIONS.md"), "content": "anything\n"}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


def test_append_only_write_whitespace_only_existing_ok(tmp_path):
    (tmp_path / "DECISIONS.md").write_text("   \n\n", encoding="utf-8")
    payload = {"file_path": str(tmp_path / "DECISIONS.md"), "content": "unrelated\n"}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


def test_append_only_write_strip_based_containment_quirk(tmp_path):
    (tmp_path / "DECISIONS.md").write_text("abc\n", encoding="utf-8")
    payload = {"file_path": str(tmp_path / "DECISIONS.md"), "content": "abc"}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


def test_append_only_write_directory_path_raises_quirk(tmp_path):
    directory = tmp_path / "DECISIONS.md"
    directory.mkdir()
    payload = {"file_path": str(directory), "content": "x"}
    with pytest.raises(IsADirectoryError):
        statutor_core.validate("write", payload, str(tmp_path), POLICY)


# --------------------------------------------------------------------------
# frozen (K-56..K-59)
# --------------------------------------------------------------------------

def test_frozen_write_denied(tmp_path):
    (tmp_path / "plans" / "archive").mkdir(parents=True)
    (tmp_path / "plans" / "archive" / "a1.md").write_text("archived\n", encoding="utf-8")
    payload = {"file_path": str(tmp_path / "plans" / "archive" / "a1.md"), "content": "changed\n"}
    result = statutor_core.validate("write", payload, str(tmp_path), POLICY)
    assert "is frozen (archived plan)" in result
    assert "immutable" in result


def test_frozen_edit_denied_even_pure_insertion(tmp_path):
    (tmp_path / "plans" / "archive").mkdir(parents=True)
    payload = {"file_path": str(tmp_path / "plans" / "archive" / "a1.md"),
               "old_string": "x", "new_string": "x\nmore"}
    result = statutor_core.validate("edit", payload, str(tmp_path), POLICY)
    assert result is not None
    assert "frozen" in result


def test_frozen_write_new_file_denied(tmp_path):
    (tmp_path / "plans" / "archive").mkdir(parents=True)
    payload = {"file_path": str(tmp_path / "plans" / "archive" / "brand_new.md"), "content": "x\n"}
    result = statutor_core.validate("write", payload, str(tmp_path), POLICY)
    assert result is not None


def test_frozen_read_ok(tmp_path):
    payload = {"file_path": str(tmp_path / "plans" / "archive" / "a1.md")}
    assert statutor_core.validate("read", payload, str(tmp_path), POLICY) is None


# --------------------------------------------------------------------------
# bash_guard (K-60..K-78)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name,expect_denied", [
    ("AGENTS.md", True), ("HANDOFF.md", True), ("DECISIONS.md", True),
    ("TASKS.md", False), ("plans/archive/x.md", False),
])
def test_bash_guard_name_set_derivation(name, expect_denied):
    result = statutor_core.guard_bash(f"tee {name}", POLICY)
    assert (result is not None) == expect_denied


def test_bash_guard_append_redirect_denied():
    result = statutor_core.guard_bash("echo x >> DECISIONS.md", POLICY)
    assert "shell write touching governed file(s)" in result
    assert "DECISIONS.md" in result
    assert "bash_guard: false" in result


def test_bash_guard_sed_i_denied():
    assert statutor_core.guard_bash("sed -i s/a/b/ HANDOFF.md", POLICY) is not None


def test_bash_guard_read_only_grep_allowed():
    assert statutor_core.guard_bash("grep foo DECISIONS.md", POLICY) is None


def test_bash_guard_strict_colocation_denied_even_devnull():
    assert statutor_core.guard_bash("grep -c x DECISIONS.md > /dev/null", POLICY) is not None


def test_bash_guard_state_policy_gap_quirk():
    assert statutor_core.guard_bash("grep -c x TASKS.md > /dev/null", POLICY) is None


def test_bash_guard_archive_glob_gap_quirk():
    assert statutor_core.guard_bash("rm plans/archive/old.md", POLICY) is None


def test_bash_guard_digit_lookbehind_ignores_fd_dup():
    assert statutor_core.guard_bash("cat DECISIONS.md 2>&1 | head", POLICY) is None


def test_bash_guard_double_append_no_digit_lookbehind_quirk():
    assert statutor_core.guard_bash("cat DECISIONS.md 2>>log", POLICY) is not None


@pytest.mark.parametrize("command", [
    "echo hi > notes.txt", "rm build.log", "cp a b",
])
def test_bash_guard_writeish_without_governed_name_allowed(command):
    assert statutor_core.guard_bash(command, POLICY) is None


def test_bash_guard_cooccurrence_false_positive():
    result = statutor_core.guard_bash("echo hi > notes.txt && cat DECISIONS.md", POLICY)
    assert result is not None


def test_bash_guard_quoted_redirect_char_denied_quirk():
    result = statutor_core.guard_bash("grep '>' AGENTS.md", POLICY)
    assert result is not None


@pytest.mark.parametrize("command", [
    "tee DECISIONS.md", "rm DECISIONS.md", "mv HANDOFF.md x", "cp AGENTS.md /tmp/x",
    "dd if=/dev/zero of=DECISIONS.md", "truncate -s0 DECISIONS.md", 'sed -i "" AGENTS.md',
])
def test_bash_guard_writeish_verbs_denied(command):
    assert statutor_core.guard_bash(command, POLICY) is not None


@pytest.mark.parametrize("command", ["add DECISIONS.md", "echo moved DECISIONS.md"])
def test_bash_guard_word_boundaries_hold(command):
    assert statutor_core.guard_bash(command, POLICY) is None


def test_bash_guard_substring_name_matching_quirk():
    assert statutor_core.guard_bash("rm MYAGENTS.mdx", POLICY) is not None


def test_bash_guard_opt_out():
    policy = {"bash_guard": False, "governed": POLICY["governed"]}
    assert statutor_core.guard_bash("echo x >> DECISIONS.md", policy) is None


def test_bash_guard_empty_command_allowed():
    assert statutor_core.guard_bash("", POLICY) is None


def test_bash_guard_missing_key_defaults_enabled():
    policy = {"governed": POLICY["governed"]}
    assert statutor_core.guard_bash("echo x >> DECISIONS.md", policy) is not None


def test_bash_guard_reached_only_via_bash_tool(tmp_path):
    assert statutor_core.validate("read", {"command": "echo x >> DECISIONS.md"}, str(tmp_path), POLICY) is None
    assert statutor_core.validate("Bash", {"command": "echo x >> DECISIONS.md"}, str(tmp_path), POLICY) is not None
    assert statutor_core.validate("bash", {}, str(tmp_path), POLICY) is None


def test_bash_guard_scans_whole_multiline_command():
    command = "echo start DECISIONS.md\n>> ignored"
    assert statutor_core.guard_bash(command, POLICY) is not None


# --------------------------------------------------------------------------
# guard_apply_patch (AP-01..AP-18) — Codex / opencode GPT-5-class edit path
# --------------------------------------------------------------------------

def envelope(*sections: str) -> dict:
    return {"command": "*** Begin Patch\n" + "\n".join(sections) + "\n*** End Patch"}


def ap(tmp_path, *sections: str) -> str | None:
    return statutor_core.validate("apply_patch", envelope(*sections), str(tmp_path), POLICY)


@pytest.mark.parametrize("command", [
    "sed -i s/a/b/ DECISIONS.md",              # a bash command, not an envelope
    "*** Update File: DECISIONS.md\n-x\n+y",   # header without Begin Patch
])
def test_apply_patch_unknown_payload_falls_through(tmp_path, command):
    """Non-envelope payloads fall through silently — the git floor covers
    whatever shape arrives; parsing here must never guess."""
    assert statutor_core.validate("apply_patch", {"command": command}, str(tmp_path), POLICY) is None


def test_apply_patch_missing_command_key_falls_through(tmp_path):
    assert statutor_core.validate("apply_patch", {}, str(tmp_path), POLICY) is None


def test_apply_patch_non_string_command_falls_through(tmp_path):
    assert statutor_core.validate("apply_patch", {"command": 42}, str(tmp_path), POLICY) is None


def test_apply_patch_non_governed_update_passes(tmp_path):
    assert ap(tmp_path, "*** Update File: src/app.py\n@@\n old\n+new") is None


def test_apply_patch_append_only_pure_addition_ok(tmp_path):
    (tmp_path / "DECISIONS.md").write_text("## D-0001\nfirst\n", encoding="utf-8")
    assert ap(tmp_path, "*** Update File: DECISIONS.md\n@@\n first\n+second") is None


def test_apply_patch_append_only_deletion_denied(tmp_path):
    result = ap(tmp_path, "*** Update File: DECISIONS.md\n@@\n-first\n+first changed")
    assert result is not None
    assert "append-only" in result
    assert "deletes/modifies 1 line(s)" in result


def test_apply_patch_append_only_add_file_ok(tmp_path):
    assert ap(tmp_path, "*** Add File: docs/DRAFT.md\n+draft notes") is None


@pytest.mark.parametrize("path,policy_name", [
    ("DECISIONS.md", "append_only"),
    ("HANDOFF.md", "overwrite_bounded"),
    ("AGENTS.md", "constitution"),
])
def test_apply_patch_delete_governed_denied(tmp_path, path, policy_name):
    result = ap(tmp_path, f"*** Delete File: {path}")
    assert result is not None
    assert f"governed ({policy_name})" in result
    assert "superseded, never removed" in result


def test_apply_patch_delete_state_file_passes_quirk(tmp_path):
    """State-plane files stay deletable everywhere (bash guard and staged
    floor share this gap by design); apply_patch matches them, not stricter."""
    assert ap(tmp_path, "*** Delete File: TASKS.md") is None


@pytest.mark.parametrize("section", [
    "*** Add File: plans/archive/new.md\n+x",
    "*** Update File: plans/archive/a1.md\n@@\n-old\n+new",
    "*** Delete File: plans/archive/a1.md",
])
def test_apply_patch_frozen_touches_denied(tmp_path, section):
    (tmp_path / "plans" / "archive").mkdir(parents=True)
    result = ap(tmp_path, section)
    assert result is not None
    assert "is frozen (archived plan)" in result


def test_apply_patch_move_out_of_archive_denied(tmp_path):
    (tmp_path / "plans" / "archive").mkdir(parents=True)
    result = ap(tmp_path,
                "*** Update File: plans/archive/a1.md",
                "*** Move to: plans/a1.md")
    assert result is not None
    assert "frozen" in result
    assert "OUT of the archive" in result


def test_apply_patch_move_into_archive_allowed(tmp_path):
    (tmp_path / "plans").mkdir()
    assert ap(tmp_path,
              "*** Update File: plans/p1.md",
              "*** Move to: plans/archive/p1.md") is None


@pytest.mark.parametrize("source,destination,policy_name", [
    ("AGENTS.md", "CONSTITUTION.md", "constitution"),
    ("HANDOFF.md", "SHIFT.md", "overwrite_bounded"),
    ("DECISIONS.md", "HISTORY.md", "append_only"),
])
def test_apply_patch_move_governed_record_to_ungoverned_path_denied(
        tmp_path, source, destination, policy_name):
    result = ap(tmp_path,
                f"*** Update File: {source}",
                f"*** Move to: {destination}")
    assert result is not None
    assert f"governed ({policy_name})" in result
    assert destination in result


def test_apply_patch_add_handoff_over_cap_denied(tmp_path):
    body = "\n".join(f"+l{i}" for i in range(41))
    result = ap(tmp_path, f"*** Add File: HANDOFF.md\n{body}")
    assert result is not None
    assert "would be 41 lines (cap 40)" in result


def test_apply_patch_add_handoff_missing_sections_denied(tmp_path):
    result = ap(tmp_path, "*** Add File: HANDOFF.md\n+# HANDOFF\n+unfilled")
    assert result is not None
    assert "missing required sections" in result
    assert "## Goal" in result


def test_apply_patch_add_compliant_handoff_ok(tmp_path):
    body = handoff()
    plus = "\n".join("+" + l for l in body.splitlines())
    assert ap(tmp_path, f"*** Add File: HANDOFF.md\n{plus}") is None


def test_apply_patch_add_agents_over_hard_cap_denied(tmp_path):
    body = "\n".join(f"+x{i}" for i in range(201))
    result = ap(tmp_path, f"*** Add File: AGENTS.md\n{body}")
    assert result is not None
    assert "would be 201 lines (hard cap 200)" in result


def test_apply_patch_update_estimated_growth_over_cap_denied(tmp_path):
    (tmp_path / "AGENTS.md").write_text(lines(195), encoding="utf-8")
    plus = "\n".join(f"+more{i}" for i in range(10))
    result = ap(tmp_path, f"*** Update File: AGENTS.md\n@@\n{plus}")
    assert result is not None
    assert "would grow to ~205 lines (cap 200)" in result


def test_apply_patch_update_estimated_growth_within_cap_ok(tmp_path):
    (tmp_path / "AGENTS.md").write_text(lines(195), encoding="utf-8")
    assert ap(tmp_path, "*** Update File: AGENTS.md\n@@\n+one\n+two") is None


def test_apply_patch_update_unreadable_target_skips_estimate(tmp_path):
    """Cap estimation needs the on-disk file; when it can't be read the
    estimate is skipped (the floor judges the final staged blob)."""
    plus = "\n".join("+x" for _ in range(300))
    assert ap(tmp_path, f"*** Update File: AGENTS.md\n@@\n{plus}") is None


def test_apply_patch_multiple_targets_first_denial_wins(tmp_path):
    (tmp_path / "plans" / "archive").mkdir(parents=True)
    result = ap(tmp_path,
                "*** Update File: DECISIONS.md\n@@\n first\n+ok",
                "*** Delete File: plans/archive/a1.md")
    assert result is not None
    assert "frozen" in result


def test_apply_patch_content_lines_starting_with_plus_star_parsed_as_content():
    targets = statutor_core._patch_targets(
        "*** Begin Patch\n*** Add File: x.md\n+*** not a header\n*** End Patch")
    assert len(targets) == 1
    assert targets[0]["content"] == ["*** not a header"]


def test_check_mode_applies_apply_patch_policy(tmp_path):
    payload = json.dumps(envelope("*** Delete File: DECISIONS.md"))
    result = run_kernel(["check", "apply_patch", payload, str(tmp_path)])
    assert result.returncode == 2
    assert "[statutor]" in result.stderr


def test_hook_mode_deny_json_for_apply_patch(tmp_path):
    event = {"tool_name": "apply_patch", "tool_input": envelope("*** Delete File: DECISIONS.md"),
             "cwd": str(tmp_path)}
    result = run_kernel(["hook"], input_str=json.dumps(event))
    assert result.returncode == 0
    data = _hook_deny_json(result)
    assert "governed (append_only)" in data["hookSpecificOutput"]["permissionDecisionReason"]


# --------------------------------------------------------------------------
# hook mode (K-79..K-87) — must fail open
# --------------------------------------------------------------------------

def _hook_deny_json(result: subprocess.CompletedProcess) -> dict:
    data = json.loads(result.stdout)
    assert data["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert data["hookSpecificOutput"]["permissionDecisionReason"].startswith("[statutor] ")
    return data


def test_hook_denies_over_cap_write(tmp_path):
    event = {"tool_name": "Write",
             "tool_input": {"file_path": str(tmp_path / "AGENTS.md"), "content": lines(201)},
             "cwd": str(tmp_path)}
    result = run_kernel(["hook"], input_str=json.dumps(event))
    assert result.returncode == 0
    _hook_deny_json(result)


def test_hook_benign_event_silent(tmp_path):
    event = {"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "AGENTS.md")},
              "cwd": str(tmp_path)}
    result = run_kernel(["hook"], input_str=json.dumps(event))
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_hook_fails_open_on_malformed_json():
    result = run_kernel(["hook"], input_str="{not json")
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_hook_fails_open_on_empty_stdin():
    result = run_kernel(["hook"], input_str="")
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_fails_open_on_non_object_json():
    result = run_kernel(["hook"], input_str="[]")
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_fails_open_on_null_tool_input(tmp_path):
    event = {"tool_name": "Write", "tool_input": None, "cwd": str(tmp_path)}
    result = run_kernel(["hook"], input_str=json.dumps(event))
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_honors_event_cwd_over_process_cwd(tmp_path):
    """The Stop/PreToolUse event's `cwd` field must be the basis for
    pattern matching, not the hook process's own OS cwd (the real
    deployment shape: the harness spawns the hook and passes cwd in the
    event, which can legitimately differ from the process's own cwd)."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    project = tmp_path / "project"
    (project / "plans" / "archive").mkdir(parents=True)
    target = project / "plans" / "archive" / "x.md"
    target.write_text("frozen\n", encoding="utf-8")
    event = {"tool_name": "Write", "tool_input": {"file_path": str(target), "content": "changed\n"},
              "cwd": str(project)}
    result = run_kernel(["hook"], cwd=str(elsewhere), input_str=json.dumps(event))
    assert result.returncode == 0
    data = _hook_deny_json(result)
    assert "frozen" in data["hookSpecificOutput"]["permissionDecisionReason"]


def test_hook_no_cwd_key_defaults_to_process_cwd_and_normalizes_camelcase(tmp_path):
    (tmp_path / "DECISIONS.md").write_text("existing\n", encoding="utf-8")
    event = {"tool_name": "Edit",
             "tool_input": {"filePath": str(tmp_path / "DECISIONS.md"),
                             "oldString": "existing", "newString": "gone"}}
    result = run_kernel(["hook"], cwd=str(tmp_path), input_str=json.dumps(event))
    assert result.returncode == 0
    _hook_deny_json(result)


@pytest.mark.parametrize("args", [["hook"], ["--claude-hook"], []])
def test_hook_mode_aliasing(tmp_path, args):
    event = {"tool_name": "Bash", "tool_input": {"command": "echo x >> DECISIONS.md"},
              "cwd": str(tmp_path)}
    result = run_kernel(args, input_str=json.dumps(event))
    assert result.returncode == 0
    data = _hook_deny_json(result)
    assert "DECISIONS.md" in data["hookSpecificOutput"]["permissionDecisionReason"]


def test_hook_fail_open_covers_kernel_bug(tmp_path):
    directory = tmp_path / "DECISIONS.md"
    directory.mkdir()
    event = {"tool_name": "Write", "tool_input": {"file_path": str(directory), "content": "x"},
              "cwd": str(tmp_path)}
    result = run_kernel(["hook"], input_str=json.dumps(event))
    assert result.returncode == 0
    assert result.stdout == ""


# --------------------------------------------------------------------------
# check mode (K-88..K-93)
# --------------------------------------------------------------------------

def test_check_over_cap_denied(tmp_path):
    payload = json.dumps({"file_path": str(tmp_path / "AGENTS.md"), "content": lines(201)})
    result = run_kernel(["check", "Write", payload, str(tmp_path)])
    assert result.returncode == 2
    assert result.stderr.startswith("[statutor] ")
    assert result.stdout == ""


def test_check_benign_allowed(tmp_path):
    payload = json.dumps({"file_path": str(tmp_path / "AGENTS.md")})
    result = run_kernel(["check", "Read", payload, str(tmp_path)])
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_check_camelcase_payload_denied(tmp_path):
    payload = json.dumps({"filePath": str(tmp_path / "DECISIONS.md"),
                           "oldString": "x", "newString": "gone"})
    result = run_kernel(["check", "Edit", payload, str(tmp_path)])
    assert result.returncode == 2
    assert "append-only" in result.stderr


@pytest.mark.parametrize("args", [["check"], ["check", "Write"]])
def test_check_usage_errors(args):
    result = run_kernel(args)
    assert result.returncode == 64
    assert "usage: statutor check TOOL JSON [CWD]" in result.stderr


def test_check_cwd_defaults_to_process_cwd(tmp_path):
    payload = json.dumps({"file_path": str(tmp_path / "AGENTS.md"), "content": lines(201)})
    result = run_kernel(["check", "Write", payload], cwd=str(tmp_path))
    assert result.returncode == 2


def test_check_honors_explicit_cwd_argument_over_process_cwd(tmp_path):
    """The documented third positional argument (`statutor check TOOL JSON
    [CWD]`) must be the basis for pattern matching, not the process's own
    OS cwd. Spawn the process somewhere unrelated and pass a different CWD
    arg pointing at the actual governed tree; only a path pattern like
    plans/archive/* (not a bare basename) can distinguish the two, since
    fnmatch matches governed basenames regardless of directory."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    project = tmp_path / "project"
    (project / "plans" / "archive").mkdir(parents=True)
    target = project / "plans" / "archive" / "x.md"
    target.write_text("frozen\n", encoding="utf-8")
    payload = json.dumps({"file_path": str(target), "content": "changed\n"})
    result = run_kernel(["check", "Write", payload, str(project)], cwd=str(elsewhere))
    assert result.returncode == 2
    assert "frozen" in result.stderr


def test_check_not_fail_open_on_invalid_json_quirk():
    result = run_kernel(["check", "Write", "{not json"])
    assert result.returncode == 1
    assert "Traceback" in result.stderr


# --------------------------------------------------------------------------
# CLI dispatch (K-94)
# --------------------------------------------------------------------------

def test_cli_unknown_mode():
    result = run_kernel(["bogus"])
    assert result.returncode == 64
    assert "typed project-ledger kernel" in result.stdout


# --------------------------------------------------------------------------
# staged / git floor (K-95..K-118)
# --------------------------------------------------------------------------

@git_required
def test_staged_clean_index_ok(ledger_repo, capsys):
    code = statutor_core.run_staged(str(ledger_repo))
    assert code == 0
    assert capsys.readouterr().out == ""


@git_required
def test_staged_pure_append_ok(ledger_repo, capsys):
    path = ledger_repo / "DECISIONS.md"
    path.write_text(path.read_text() + "\n## D-0002\nsecond\n", encoding="utf-8")
    git(ledger_repo, "add", "DECISIONS.md")
    code = statutor_core.run_staged(str(ledger_repo))
    assert code == 0
    assert capsys.readouterr().out == ""


@git_required
def test_staged_deletion_denied(ledger_repo, capsys):
    path = ledger_repo / "DECISIONS.md"
    text = path.read_text()
    path.write_text("".join(text.splitlines(keepends=True)[:-1]), encoding="utf-8")
    git(ledger_repo, "add", "DECISIONS.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert ("DECISIONS.md: append-only, but staged content deletes, rewrites, "
            "or reorders existing lines.") in out


@git_required
def test_staged_in_place_modification_counts_as_deletion(ledger_repo, capsys):
    path = ledger_repo / "DECISIONS.md"
    path.write_text(path.read_text().replace("first", "changed"), encoding="utf-8")
    git(ledger_repo, "add", "DECISIONS.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert ("DECISIONS.md: append-only, but staged content deletes, rewrites, "
            "or reorders existing lines.") in out


@git_required
def test_staged_whole_file_rm_denied(ledger_repo, capsys):
    git(ledger_repo, "rm", "-q", "DECISIONS.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "DECISIONS.md: governed (append_only) record cannot be deleted" in out


@pytest.mark.parametrize("path,policy_name", [
    ("AGENTS.md", "constitution"),
    ("HANDOFF.md", "overwrite_bounded"),
    ("TASKS.md", "state"),
])
@git_required
def test_staged_governed_record_file_deletion_denied(
        ledger_repo, capsys, path, policy_name):
    git(ledger_repo, "rm", "-q", path)
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert f"{path}: governed ({policy_name}) record cannot be deleted" in out


@pytest.mark.parametrize("source,destination,policy_name", [
    ("AGENTS.md", "CONSTITUTION.md", "constitution"),
    ("HANDOFF.md", "SHIFT.md", "overwrite_bounded"),
    ("DECISIONS.md", "HISTORY.md", "append_only"),
    ("TASKS.md", "BACKLOG.md", "state"),
])
@git_required
def test_staged_governed_record_rename_out_denied(
        ledger_repo, capsys, source, destination, policy_name):
    git(ledger_repo, "mv", source, destination)
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert f"{source}: governed ({policy_name}) record cannot move" in out
    assert destination in out


@git_required
def test_staged_governed_rename_within_same_rule_allowed(ledger_repo, capsys):
    (ledger_repo / "docs").mkdir()
    git(ledger_repo, "mv", "DECISIONS.md", "docs/DECISIONS.md")
    code = statutor_core.run_staged(str(ledger_repo))
    assert code == 0
    assert capsys.readouterr().out == ""


@git_required
def test_staged_no_trailing_newline_append_reads_as_deletion_quirk(tmp_path, capsys):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001\nfirst", encoding="utf-8")
    commit_all(tmp_path)
    old = (tmp_path / "DECISIONS.md").read_text()
    (tmp_path / "DECISIONS.md").write_text(old + "\n## D-0002\nsecond\n", encoding="utf-8")
    git(tmp_path, "add", "DECISIONS.md")
    code = statutor_core.run_staged(str(tmp_path))
    out = capsys.readouterr().out
    assert code == 1
    assert "append-only, but staged content deletes, rewrites" in out


@git_required
def test_staged_append_only_insertion_between_existing_lines_allowed(
        ledger_repo, capsys):
    path = ledger_repo / "DECISIONS.md"
    path.write_text(path.read_text().replace(
        "# DECISIONS\n\n", "# DECISIONS\ninserted context\n\n"), encoding="utf-8")
    git(ledger_repo, "add", "DECISIONS.md")
    code = statutor_core.run_staged(str(ledger_repo))
    assert code == 0
    assert capsys.readouterr().out == ""


@git_required
def test_staged_append_only_binary_rewrite_denied(ledger_repo, capsys):
    (ledger_repo / "DECISIONS.md").write_bytes(b"rewritten\x00binary\n")
    git(ledger_repo, "add", "DECISIONS.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "append-only, but staged content deletes, rewrites" in out


@git_required
def test_staged_append_only_ignores_unstaged_diff_attribute(ledger_repo, capsys):
    (ledger_repo / ".gitattributes").write_text(
        "DECISIONS.md -diff\n", encoding="utf-8")
    (ledger_repo / "DECISIONS.md").write_text(
        "# DECISIONS\n\nwholesale rewrite\n", encoding="utf-8")
    git(ledger_repo, "add", "DECISIONS.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "append-only, but staged content deletes, rewrites" in out


@git_required
def test_staged_first_time_add_all_additions_ok(tmp_path, capsys):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001\nfirst\n", encoding="utf-8")
    git(tmp_path, "add", "DECISIONS.md")
    code = statutor_core.run_staged(str(tmp_path))
    assert code == 0
    assert capsys.readouterr().out == ""


@git_required
def test_staged_archive_modification_frozen_denied(ledger_repo, capsys):
    (ledger_repo / "plans" / "archive" / "a1.md").write_text("tampered\n", encoding="utf-8")
    git(ledger_repo, "add", "plans/archive/a1.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert ("plans/archive/a1.md: frozen — archived records are immutable "
            "(moving a plan INTO the archive is allowed).") in out


@git_required
def test_staged_archive_deletion_frozen_denied(ledger_repo, capsys):
    git(ledger_repo, "rm", "-q", "plans/archive/a1.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "plans/archive/a1.md: frozen" in out


@git_required
def test_staged_new_file_added_under_archive_denied(ledger_repo, capsys):
    (ledger_repo / "plans" / "archive" / "brand_new.md").write_text("x\n", encoding="utf-8")
    git(ledger_repo, "add", "plans/archive/brand_new.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "direct additions to the archive are denied" in out


@git_required
def test_staged_rename_into_archive_allowed(ledger_repo, capsys):
    git(ledger_repo, "mv", "plans/p1.md", "plans/archive/p1.md")
    code = statutor_core.run_staged(str(ledger_repo))
    assert code == 0
    assert capsys.readouterr().out == ""


@git_required
def test_staged_rename_departure_from_archive_denied(ledger_repo, capsys):
    git(ledger_repo, "mv", "plans/archive/a1.md", "plans/a1.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "plans/archive/a1.md: frozen" in out


@git_required
def test_staged_rename_within_archive_single_violation(ledger_repo, capsys):
    git(ledger_repo, "mv", "plans/archive/a1.md", "plans/archive/a2.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert out.count("frozen") == 1
    assert "plans/archive/a1.md" in out


@git_required
def test_staged_handoff_over_cap(ledger_repo, capsys):
    (ledger_repo / "HANDOFF.md").write_text(handoff_padded(52), encoding="utf-8")
    git(ledger_repo, "add", "HANDOFF.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "HANDOFF.md: staged version is 52 lines (cap 40)." in out


@git_required
def test_staged_handoff_missing_section_list_repr(ledger_repo, capsys):
    (ledger_repo / "HANDOFF.md").write_text(handoff(drop=("## Gotchas",)), encoding="utf-8")
    git(ledger_repo, "add", "HANDOFF.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "HANDOFF.md: missing sections ['## Gotchas']." in out


@git_required
def test_staged_agents_over_cap_falls_back_to_hard_max_lines(ledger_repo, capsys):
    (ledger_repo / "AGENTS.md").write_text(lines(251), encoding="utf-8")
    git(ledger_repo, "add", "AGENTS.md")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "AGENTS.md: staged version is 251 lines (cap 200)." in out


@git_required
def test_staged_constitution_rule_without_max_lines_falls_back_to_200(tmp_path, capsys, monkeypatch):
    """rule.get('max_lines', rule.get('hard_max_lines', 200)) — the literal
    200 backstop is unreachable under DEFAULT_POLICY (its constitution rule
    always carries hard_max_lines), so it needs a custom governed rule that
    omits both keys to exercise at all."""
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "AGENTS.md").write_text("short\n", encoding="utf-8")
    commit_all(tmp_path)
    (tmp_path / "AGENTS.md").write_text(lines(201), encoding="utf-8")
    git(tmp_path, "add", "AGENTS.md")
    monkeypatch.setattr(statutor_core, "load_policy",
                         lambda cwd: {"governed": [{"pattern": "AGENTS.md", "policy": "constitution"}]})
    code = statutor_core.run_staged(str(tmp_path))
    out = capsys.readouterr().out
    assert code == 1
    assert "AGENTS.md: staged version is 201 lines (cap 200)." in out


@git_required
def test_staged_tasks_deletion_unchecked_gap_quirk(ledger_repo, capsys):
    (ledger_repo / "TASKS.md").write_text("- [ ] T-0001 one\n", encoding="utf-8")
    git(ledger_repo, "add", "TASKS.md")
    code = statutor_core.run_staged(str(ledger_repo))
    assert code == 0
    assert capsys.readouterr().out == ""


@git_required
def test_staged_unstaged_worktree_violations_ignored(ledger_repo, capsys):
    (ledger_repo / "DECISIONS.md").write_text("truncated\n", encoding="utf-8")
    (ledger_repo / "plans" / "archive" / "a1.md").write_text("tampered\n", encoding="utf-8")
    code = statutor_core.run_staged(str(ledger_repo))
    assert code == 0
    assert capsys.readouterr().out == ""


@git_required
def test_staged_three_violations_frozen_first(ledger_repo, capsys):
    (ledger_repo / "plans" / "archive" / "a1.md").write_text("tampered\n", encoding="utf-8")
    (ledger_repo / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001\n", encoding="utf-8")
    (ledger_repo / "HANDOFF.md").write_text(handoff_padded(48), encoding="utf-8")
    git(ledger_repo, "add", "-A")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    out_lines = [l for l in out.splitlines() if l.strip()]
    assert len(out_lines) == 3
    assert "frozen" in out_lines[0]


@git_required
def test_staged_not_a_git_repo_fails_closed(tmp_path, capsys):
    code = statutor_core.run_staged(str(tmp_path))
    out = capsys.readouterr().out
    assert code == 1
    assert "git rev-parse --is-inside-work-tree failed" in out
    assert "non-bare Git worktree with a readable index" in out


@git_required
def test_staged_bare_repo_fails_closed(tmp_path, capsys):
    git(tmp_path, "init", "--bare", "-q", ".")
    code = statutor_core.run_staged(str(tmp_path))
    out = capsys.readouterr().out
    assert code == 1
    assert "reported no worktree" in out
    assert "non-bare Git worktree" in out


@git_required
def test_staged_missing_index_fails_closed(ledger_repo, capsys):
    os.unlink(ledger_repo / ".git" / "index")
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "record cannot be deleted" in out or "git " in out


@git_required
def test_staged_cli_dispatch(ledger_repo):
    (ledger_repo / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001\n", encoding="utf-8")
    git(ledger_repo, "add", "DECISIONS.md")
    result = run_kernel(["staged"], cwd=str(ledger_repo))
    assert result.returncode == 1
    result2 = run_kernel(["--staged", str(ledger_repo)])
    assert result2.returncode == 1


@git_required
def test_staged_cli_dispatch_clean(ledger_repo):
    result = run_kernel(["staged"], cwd=str(ledger_repo))
    assert result.returncode == 0


@git_required
def test_staged_nested_docs_decisions_governed_by_basename(tmp_path, capsys):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "DECISIONS.md").write_text("# DECISIONS\n\nfirst\nsecond\n", encoding="utf-8")
    commit_all(tmp_path)
    (tmp_path / "docs" / "DECISIONS.md").write_text("# DECISIONS\n\nfirst\n", encoding="utf-8")
    git(tmp_path, "add", "docs/DECISIONS.md")
    code = statutor_core.run_staged(str(tmp_path))
    out = capsys.readouterr().out
    assert code == 1
    assert "docs/DECISIONS.md: append-only" in out


@git_required
def test_staged_repo_local_statutor_yaml_governed_empty(tmp_path, capsys):
    pytest.importorskip("yaml")
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "DECISIONS.md").write_text("# DECISIONS\n\nfirst\nsecond\n", encoding="utf-8")
    (tmp_path / ".statutor.yaml").write_text("governed: []\n", encoding="utf-8")
    commit_all(tmp_path)
    (tmp_path / "DECISIONS.md").write_text("# DECISIONS\n\nfirst\n", encoding="utf-8")
    git(tmp_path, "add", "DECISIONS.md")
    code = statutor_core.run_staged(str(tmp_path))
    assert code == 0
    assert capsys.readouterr().out == ""


@git_required
def test_staged_color_ui_always_config_still_detects_deletions(ledger_repo, capsys, monkeypatch, tmp_path):
    """A hostile color config cannot affect NUL metadata or raw blob checks."""
    colorful_gitconfig = tmp_path / "colorful.gitconfig"
    colorful_gitconfig.write_text("[color]\n\tui = always\n", encoding="utf-8")
    path = ledger_repo / "DECISIONS.md"
    text = path.read_text()
    path.write_text("".join(text.splitlines(keepends=True)[:-1]), encoding="utf-8")
    git(ledger_repo, "add", "DECISIONS.md")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(colorful_gitconfig))
    code = statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    assert code == 1
    assert "append-only, but staged content deletes, rewrites" in out


@git_required
def test_staged_output_prefix_format(ledger_repo, capsys):
    git(ledger_repo, "rm", "-q", "plans/archive/a1.md")
    statutor_core.run_staged(str(ledger_repo))
    out = capsys.readouterr().out
    for line in out.splitlines():
        if line:
            assert line.startswith("STATUTOR  ")


def commit_trust_roots(repo: Path, *, managed_bridge: bool = False) -> None:
    (repo / ".statutor.yaml").write_text(
        statutor_core.TEMPLATES[".statutor.yaml"], encoding="utf-8")
    if managed_bridge:
        (repo / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    commit_all(repo, "trust roots")


@git_required
def test_staged_unstaged_policy_weakening_cannot_disable_head_rules(
        ledger_repo, capsys):
    commit_trust_roots(ledger_repo)
    (ledger_repo / ".statutor.yaml").write_text("governed: []\n", encoding="utf-8")
    (ledger_repo / "DECISIONS.md").write_text("rewritten\n", encoding="utf-8")
    git(ledger_repo, "add", "DECISIONS.md")
    assert statutor_core.run_staged(str(ledger_repo)) == 1
    out = capsys.readouterr().out
    assert "append-only" in out
    assert "trust-root change" not in out


@git_required
def test_staged_costaged_weakening_needs_receipt_and_cannot_relax_baseline(
        ledger_repo, capsys):
    commit_trust_roots(ledger_repo)
    (ledger_repo / ".statutor.yaml").write_text("governed: []\n", encoding="utf-8")
    (ledger_repo / "DECISIONS.md").write_text("rewritten\n", encoding="utf-8")
    git(ledger_repo, "add", ".statutor.yaml", "DECISIONS.md")
    assert statutor_core.run_staged(str(ledger_repo)) == 1
    out = capsys.readouterr().out
    assert "trust-root change requires" in out
    assert "append-only" in out


@git_required
def test_staged_policy_only_change_requires_exact_tree_receipt(ledger_repo, capsys):
    commit_trust_roots(ledger_repo)
    path = ledger_repo / ".statutor.yaml"
    path.write_text(path.read_text() + "\n", encoding="utf-8")
    git(ledger_repo, "add", ".statutor.yaml")
    assert statutor_core.run_staged(str(ledger_repo)) == 1
    assert "missing, stale, or unsafe receipt" in capsys.readouterr().out


@git_required
def test_staged_candidate_policy_is_strict_parse_error(ledger_repo, capsys):
    commit_trust_roots(ledger_repo)
    (ledger_repo / ".statutor.yaml").write_text("unknown: true\ngoverned: []\n", encoding="utf-8")
    git(ledger_repo, "add", ".statutor.yaml")
    assert statutor_core.run_staged(str(ledger_repo)) == 1
    assert ":.statutor.yaml: invalid or unsupported" in capsys.readouterr().out


@git_required
def test_staged_bootstrap_candidate_policy_judges_same_transaction(tmp_path, capsys):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "NOTES.md").write_text("original\n", encoding="utf-8")
    commit_all(tmp_path, "unmanaged note")
    (tmp_path / ".statutor.yaml").write_text(
        "governed:\n  - pattern: NOTES.md\n    policy: append_only\n", encoding="utf-8")
    (tmp_path / "NOTES.md").write_text("rewritten\n", encoding="utf-8")
    git(tmp_path, "add", ".statutor.yaml", "NOTES.md")
    assert statutor_core.run_staged(str(tmp_path)) == 1
    out = capsys.readouterr().out
    assert "NOTES.md: append-only" in out
    assert "trust-root change" not in out


@git_required
def test_staged_managed_claude_bridge_change_requires_receipt(ledger_repo, capsys):
    commit_trust_roots(ledger_repo, managed_bridge=True)
    (ledger_repo / "CLAUDE.md").write_text("# replacement\n", encoding="utf-8")
    git(ledger_repo, "add", "CLAUDE.md")
    assert statutor_core.run_staged(str(ledger_repo)) == 1
    assert "['CLAUDE.md']" in capsys.readouterr().out


@git_required
def test_staged_unmanaged_claude_file_remains_human_owned(ledger_repo, capsys):
    (ledger_repo / "CLAUDE.md").write_text("# human\n", encoding="utf-8")
    commit_trust_roots(ledger_repo)
    (ledger_repo / "CLAUDE.md").write_text("# human changed\n", encoding="utf-8")
    git(ledger_repo, "add", "CLAUDE.md")
    assert statutor_core.run_staged(str(ledger_repo)) == 0
    assert capsys.readouterr().out == ""


@git_required
def test_trust_approve_writes_mode_0600_exact_tree_receipt(ledger_repo, capsys):
    commit_trust_roots(ledger_repo)
    path = ledger_repo / ".statutor.yaml"
    path.write_text(path.read_text().replace("hard_max_lines: 200", "hard_max_lines: 190"),
                    encoding="utf-8")
    git(ledger_repo, "add", ".statutor.yaml")
    _, _, snapshots = statutor_core._policy_snapshots(str(ledger_repo))
    reserved = statutor_core._reserved_changes(str(ledger_repo), snapshots)
    tree = statutor_core._trust_context(str(ledger_repo), snapshots, reserved)["index_tree_oid"]
    code = statutor_core.run_trust_approve([
        str(ledger_repo), "--decision", "D-0015", "--reason", "tighten cap",
        "--confirm-tree", tree,
    ])
    assert code == 0
    capsys.readouterr()
    receipt = Path(statutor_core._git_local_path(
        str(ledger_repo), "statutor/trust-receipt.json"))
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert statutor_core.run_staged(str(ledger_repo)) == 0
    assert capsys.readouterr().out == ""


@git_required
def test_trust_receipt_expires_when_index_tree_changes(ledger_repo, capsys):
    commit_trust_roots(ledger_repo)
    path = ledger_repo / ".statutor.yaml"
    path.write_text(path.read_text().replace("hard_max_lines: 200", "hard_max_lines: 190"),
                    encoding="utf-8")
    git(ledger_repo, "add", ".statutor.yaml")
    _, _, snapshots = statutor_core._policy_snapshots(str(ledger_repo))
    reserved = statutor_core._reserved_changes(str(ledger_repo), snapshots)
    tree = statutor_core._trust_context(str(ledger_repo), snapshots, reserved)["index_tree_oid"]
    assert statutor_core.run_trust_approve([
        str(ledger_repo), "--decision", "D-0015", "--reason", "tighten cap",
        "--confirm-tree", tree]) == 0
    capsys.readouterr()
    (ledger_repo / "README.tmp").write_text("later\n", encoding="utf-8")
    git(ledger_repo, "add", "README.tmp")
    assert statutor_core.run_staged(str(ledger_repo)) == 1
    assert "stale" in capsys.readouterr().out


def test_policy_change_classifier_is_conservative():
    base = copy.deepcopy(statutor_core.DEFAULT_POLICY)
    tighter = copy.deepcopy(base)
    tighter["governed"][0]["hard_max_lines"] = 190
    assert statutor_core._policy_change_class(base, tighter) == "non-weakening"
    weaker = copy.deepcopy(base)
    weaker["governed"].pop()
    assert statutor_core._policy_change_class(base, weaker) == "weakening-or-incomparable"


# --------------------------------------------------------------------------
# init (K-119..K-126)
# --------------------------------------------------------------------------

def test_init_creates_all_templates_byte_identical(tmp_path):
    code = statutor_core.run_init(str(tmp_path))
    assert code == 0
    for name, body in statutor_core.TEMPLATES.items():
        assert (tmp_path / name).read_text(encoding="utf-8") == body
    assert (tmp_path / "CLAUDE.md").exists()


def test_init_claude_md_content(tmp_path):
    statutor_core.run_init(str(tmp_path))
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"


def test_init_directory_scaffolding(tmp_path):
    statutor_core.run_init(str(tmp_path))
    assert (tmp_path / "plans" / "archive").is_dir()
    assert (tmp_path / "notes").is_dir()


def test_init_stdout_lines_fresh(tmp_path, capsys):
    statutor_core.run_init(str(tmp_path))
    out = capsys.readouterr().out.splitlines()
    expected = [f"write {name}" for name in statutor_core.TEMPLATES] + ["write CLAUDE.md (@AGENTS.md import)"]
    assert out == expected
    assert len(out) == 7


def test_init_idempotent_second_run(tmp_path, capsys):
    statutor_core.run_init(str(tmp_path))
    contents_before = {name: (tmp_path / name).read_bytes() for name in statutor_core.TEMPLATES}
    capsys.readouterr()
    code = statutor_core.run_init(str(tmp_path))
    out = capsys.readouterr().out.splitlines()
    assert code == 0
    expected = [f"skip  {name} (exists)" for name in statutor_core.TEMPLATES]
    assert out == expected
    assert "CLAUDE.md" not in "\n".join(out)
    for name in statutor_core.TEMPLATES:
        assert (tmp_path / name).read_bytes() == contents_before[name]


def test_init_preserves_existing_claude_md(tmp_path, capsys):
    (tmp_path / "CLAUDE.md").write_text("# my own notes\n", encoding="utf-8")
    capsys.readouterr()
    statutor_core.run_init(str(tmp_path))
    out = capsys.readouterr().out
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "# my own notes\n"
    assert "CLAUDE.md" not in out


def test_init_cli_dispatch_default_dir(tmp_path):
    result = run_kernel(["init"], cwd=str(tmp_path))
    assert result.returncode == 0
    assert (tmp_path / "AGENTS.md").exists()


def test_init_scaffolded_statutor_yaml_round_trips(tmp_path):
    pytest.importorskip("yaml")
    statutor_core.run_init(str(tmp_path))
    policy = statutor_core.load_policy(str(tmp_path))
    assert policy["bash_guard"] is True
    assert policy["governed"] == statutor_core.DEFAULT_POLICY["governed"]


# --------------------------------------------------------------------------
# templates (K-127..K-132)
# --------------------------------------------------------------------------

def test_template_agents_within_cap():
    content = statutor_core.TEMPLATES["AGENTS.md"]
    assert content.count("\n") + 1 <= 200


def test_template_handoff_within_cap_and_has_sections():
    content = statutor_core.TEMPLATES["HANDOFF.md"]
    assert content.count("\n") + 1 <= 40
    for section in REQUIRED_SECTIONS:
        assert section in content


def test_template_decisions_self_containment(tmp_path):
    template = statutor_core.TEMPLATES["DECISIONS.md"]
    (tmp_path / "DECISIONS.md").write_text(template, encoding="utf-8")
    payload = {"file_path": str(tmp_path / "DECISIONS.md"), "content": template}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


@pytest.mark.parametrize("name", [k for k in statutor_core.TEMPLATES if k.endswith(".md")])
def test_template_each_markdown_key_passes_own_policy(tmp_path, name):
    payload = {"file_path": str(tmp_path / name), "content": statutor_core.TEMPLATES[name]}
    assert statutor_core.validate("write", payload, str(tmp_path), POLICY) is None


def test_template_statutor_yaml_matches_default_policy():
    yaml = pytest.importorskip("yaml")
    parsed = yaml.safe_load(statutor_core.TEMPLATES[".statutor.yaml"])
    assert parsed == statutor_core.DEFAULT_POLICY


def test_templates_key_set_and_no_templates_dir():
    assert set(statutor_core.TEMPLATES.keys()) == {
        "AGENTS.md", "HANDOFF.md", "DECISIONS.md", "TASKS.md", "ROADMAP.md", ".statutor.yaml"}
    assert not (REPO_ROOT / "templates").exists()
