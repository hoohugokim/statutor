"""Scenario builders for the Rust↔Python staged-floor conformance suite.

Each builder populates an isolated git repo (tmp_path) and leaves specific
changes STAGED. The differential test runs both kernels against the result
and asserts byte-identical verdicts — Python is normative (D-0014).

Self-contained: its own sys.path bootstrap and git-env isolation, mirroring
test_kernel.py's guards.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys_path_core = str(REPO_ROOT / "core")
if sys_path_core not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path_core)

GIT_ENV = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}

HANDOFF_BODY = (
    "# H\nlast_verified: 2026-08-24 by t\n\n## Goal\ng\n\n"
    "## Last verified state\ns\n\n## Next action\nn\n\n"
    "## Gotchas\ngo\n\n## Do not touch\nd\n"
)


def git(cwd, *args) -> None:
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    *args], cwd=str(cwd), env=GIT_ENV,
                   capture_output=True, text=True, check=True)


def init_repo(root: Path) -> None:
    git(root, "init", "-q", "-b", "main")


def base_ledger(root: Path) -> None:
    """Standard committed ledger: DECISIONS/HANDOFF/AGENTS/TASKS + plans."""
    init_repo(root)
    (root / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001\nkeep\n", encoding="utf-8")
    (root / "HANDOFF.md").write_text(HANDOFF_BODY, encoding="utf-8")
    (root / "AGENTS.md").write_text("# AGENTS\nshort\n", encoding="utf-8")
    (root / "TASKS.md").write_text("- [ ] T-0001 one\n", encoding="utf-8")
    (root / "plans" / "archive").mkdir(parents=True, exist_ok=True)
    (root / "plans" / "archive" / "a.md").write_text("archived\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")


def drop_last_line(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(lines[:-1]), encoding="utf-8")


# --------------------------------------------------------------------------
# builders: name -> fn(root: Path) -> None (leaves desired changes staged)
# --------------------------------------------------------------------------

def s01_clean_index(root: Path) -> None:
    base_ledger(root)


def s02_pure_append(root: Path) -> None:
    base_ledger(root)
    p = root / "DECISIONS.md"
    p.write_text(p.read_text() + "\n## D-0002\nsecond\n", encoding="utf-8")
    git(root, "add", "DECISIONS.md")


def s03_delete_last_line(root: Path) -> None:
    base_ledger(root)
    drop_last_line(root / "DECISIONS.md")
    git(root, "add", "DECISIONS.md")


def s04_in_place_modify(root: Path) -> None:
    base_ledger(root)
    p = root / "DECISIONS.md"
    p.write_text(p.read_text().replace("keep", "changed"), encoding="utf-8")
    git(root, "add", "DECISIONS.md")


def s05_rm_whole_file(root: Path) -> None:
    base_ledger(root)
    git(root, "rm", "-q", "DECISIONS.md")


def s06_append_no_trailing_newline(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    init_repo(root)
    (root / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001\nkeep", encoding="utf-8")
    git(root, "add", "-A"); git(root, "commit", "-q", "-m", "i")
    p = root / "DECISIONS.md"
    p.write_text(p.read_text() + "\n## D-0002\nsecond\n", encoding="utf-8")
    git(root, "add", "DECISIONS.md")


def s07_first_time_add(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    init_repo(root)
    (root / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001\nkeep\n", encoding="utf-8")
    git(root, "add", "DECISIONS.md")


def s08_archive_tamper(root: Path) -> None:
    base_ledger(root)
    p = root / "plans" / "archive" / "a.md"
    p.write_text("tampered\n", encoding="utf-8")
    git(root, "add", "plans/archive/a.md")


def s09_archive_delete(root: Path) -> None:
    base_ledger(root)
    git(root, "rm", "-q", "plans/archive/a.md")


def s10_archive_direct_add(root: Path) -> None:
    base_ledger(root)
    (root / "plans" / "archive" / "new.md").write_text("x\n", encoding="utf-8")
    git(root, "add", "plans/archive/new.md")


def s11_rename_into_archive(root: Path) -> None:
    base_ledger(root)
    (root / "plans" / "p.md").write_text("plan\n", encoding="utf-8")
    git(root, "add", "plans/p.md"); git(root, "commit", "-q", "-m", "p")
    git(root, "mv", "plans/p.md", "plans/archive/p.md")


def s12_rename_out_of_archive(root: Path) -> None:
    base_ledger(root)
    git(root, "mv", "plans/archive/a.md", "plans/a.md")


def s13_rename_within_archive(root: Path) -> None:
    base_ledger(root)
    git(root, "mv", "plans/archive/a.md", "plans/archive/b.md")


def s14_handoff_over_cap(root: Path) -> None:
    base_ledger(root)
    (root / "HANDOFF.md").write_text(
        "\n".join(f"l{i}" for i in range(52)) + "\n", encoding="utf-8")
    git(root, "add", "HANDOFF.md")


def s15_handoff_at_cap_ok(root: Path) -> None:
    base_ledger(root)
    body = ["# H"]
    for sec in ("## Goal", "## Last verified state", "## Next action",
                "## Gotchas", "## Do not touch"):
        body += [sec, "x"]
    filler = 40 - len(body)
    body += [f"f{i}" for i in range(filler)]
    (root / "HANDOFF.md").write_text("\n".join(body) + "\n", encoding="utf-8")
    git(root, "add", "HANDOFF.md")


def s16_handoff_missing_section(root: Path) -> None:
    base_ledger(root)
    text = HANDOFF_BODY.replace("## Gotchas\ngo\n\n", "")
    (root / "HANDOFF.md").write_text(text, encoding="utf-8")
    git(root, "add", "HANDOFF.md")


def s17_handoff_over_cap_and_missing_sections(root: Path) -> None:
    base_ledger(root)
    # Over cap AND lacking two sections: cap line precedes sections line.
    (root / "HANDOFF.md").write_text(
        "\n".join(f"l{i}" for i in range(50)) + "\n", encoding="utf-8")
    git(root, "add", "HANDOFF.md")


def s18_agents_over_hard_cap(root: Path) -> None:
    base_ledger(root)
    (root / "AGENTS.md").write_text(
        "\n".join(f"x{i}" for i in range(251)) + "\n", encoding="utf-8")
    git(root, "add", "AGENTS.md")


def s19_constitution_no_max_backstop_200(root: Path) -> None:
    base_ledger(root)
    (root / ".statutor.yaml").write_text(
        "governed:\n"
        "  - pattern: AGENTS.md\n"
        "    policy: constitution\n",
        encoding="utf-8")
    git(root, "add", ".statutor.yaml"); git(root, "commit", "-q", "-m", "cfg")
    (root / "AGENTS.md").write_text(
        "\n".join(f"x{i}" for i in range(201)) + "\n", encoding="utf-8")
    git(root, "add", "AGENTS.md")


def s20_tasks_truncate_unchecked(root: Path) -> None:
    base_ledger(root)
    (root / "TASKS.md").write_text("- [ ] T-0001 one\n", encoding="utf-8")
    git(root, "add", "TASKS.md")


def s21_unstaged_ignored(root: Path) -> None:
    base_ledger(root)
    p = root / "DECISIONS.md"
    p.write_text("truncated\n", encoding="utf-8")  # unstaged tamper
    q = root / "plans" / "archive" / "a.md"
    q.write_text("tampered\n", encoding="utf-8")   # unstaged tamper


def s22_three_violations_frozen_first(root: Path) -> None:
    base_ledger(root)
    (root / "plans" / "archive" / "a.md").write_text("tampered\n", encoding="utf-8")
    d = root / "DECISIONS.md"
    d.write_text("# DECISIONS\n\n## D-0001\n", encoding="utf-8")
    (root / "HANDOFF.md").write_text("\n".join(f"l{i}" for i in range(48)) + "\n",
                                     encoding="utf-8")
    git(root, "add", "-A")


def s23_not_a_git_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "DECISIONS.md").write_text("whatever\n", encoding="utf-8")


def s24_nested_docs_decisions_basename(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    init_repo(root)
    (root / "docs").mkdir()
    (root / "docs" / "DECISIONS.md").write_text("# DECISIONS\n\nfirst\nsecond\n",
                                                encoding="utf-8")
    git(root, "add", "-A"); git(root, "commit", "-q", "-m", "i")
    p = root / "docs" / "DECISIONS.md"
    p.write_text("# DECISIONS\n\nfirst\n", encoding="utf-8")
    git(root, "add", "docs/DECISIONS.md")


def s25_statutor_yaml_governed_empty(root: Path) -> None:
    base_ledger(root)
    (root / ".statutor.yaml").write_text("governed: []\n", encoding="utf-8")
    git(root, "add", ".statutor.yaml"); git(root, "commit", "-q", "-m", "cfg")
    p = root / "DECISIONS.md"
    p.write_text(p.read_text().replace("keep", "gone"), encoding="utf-8")
    git(root, "add", "DECISIONS.md")


def s26_new_append_only_with_minus_lines_content(root: Path) -> None:
    """A brand-new append_only file whose content itself contains '-'-prefixed
    lines: unified diff shows additions only, so zero 'deletions'."""
    root.mkdir(parents=True, exist_ok=True)
    init_repo(root)
    (root / "NOTES.md").write_text("- item\n- another\n", encoding="utf-8")
    (root / ".statutor.yaml").write_text(
        "governed:\n  - pattern: NOTES.md\n    policy: append_only\n",
        encoding="utf-8")
    git(root, "add", "-A")


def s27_rename_r100_exact(root: Path) -> None:
    base_ledger(root)
    git(root, "mv", "TASKS.md", "JOURNAL.md")


def s28_new_handoff_missing_sections_blob_check(root: Path) -> None:
    """Staged ADD of an overwrite_bounded file: caps/sections judged on the
    full staged blob even though it is a first arrival."""
    base_ledger(root)
    (root / "HANDOFF.md").write_text("# H\npartial\n", encoding="utf-8")
    git(root, "add", "HANDOFF.md")


def s29_statutor_yaml_custom_names(root: Path) -> None:
    """Policy renames the planes: BACKLOG.md is the state file, CHOICES.md is
    append-only; TASKS.md/DECISIONS.md become ungoverned."""
    base_ledger(root)
    (root / ".statutor.yaml").write_text(
        "governed:\n"
        "  - pattern: AGENTS.md\n    policy: constitution\n    hard_max_lines: 200\n"
        "  - pattern: HANDOFF.md\n    policy: overwrite_bounded\n    max_lines: 40\n"
        "    required_sections:\n      - \"## Goal\"\n"
        "  - pattern: CHOICES.md\n    policy: append_only\n"
        "  - pattern: BACKLOG.md\n    policy: state\n",
        encoding="utf-8")
    git(root, "add", ".statutor.yaml"); git(root, "commit", "-q", "-m", "cfg")
    c = root / "CHOICES.md"
    c.write_text("# CHOICES\n\n## C-0001\nhold\n", encoding="utf-8")
    git(root, "add", "CHOICES.md")
    # Violate the renamed append-only file AND truncate the now-ungoverned one.
    drop_last_line(c)
    git(root, "add", "CHOICES.md")
    d = root / "DECISIONS.md"
    d.write_text("gone\n", encoding="utf-8")
    git(root, "add", "DECISIONS.md")


def s30_malformed_statutor_yaml_falls_back(root: Path) -> None:
    """Unparseable policy file: both kernels must fall back to embedded
    defaults rather than crash or silently unguard."""
    base_ledger(root)
    (root / ".statutor.yaml").write_text("::: not yaml [\n", encoding="utf-8")
    git(root, "add", ".statutor.yaml"); git(root, "commit", "-q", "-m", "cfg")
    drop_last_line(root / "DECISIONS.md")
    git(root, "add", "DECISIONS.md")


def s31_delete_agents_record(root: Path) -> None:
    base_ledger(root)
    git(root, "rm", "-q", "AGENTS.md")


def s32_rename_agents_out(root: Path) -> None:
    base_ledger(root)
    git(root, "mv", "AGENTS.md", "CONSTITUTION.md")


def s33_delete_handoff_record(root: Path) -> None:
    base_ledger(root)
    git(root, "rm", "-q", "HANDOFF.md")


def s34_rename_handoff_out(root: Path) -> None:
    base_ledger(root)
    git(root, "mv", "HANDOFF.md", "SHIFT.md")


def s35_rename_decisions_out(root: Path) -> None:
    base_ledger(root)
    git(root, "mv", "DECISIONS.md", "HISTORY.md")


def s36_delete_tasks_record(root: Path) -> None:
    base_ledger(root)
    git(root, "rm", "-q", "TASKS.md")


def s37_append_only_binary_rewrite(root: Path) -> None:
    base_ledger(root)
    (root / "DECISIONS.md").write_bytes(b"rewritten\x00binary\n")
    git(root, "add", "DECISIONS.md")


def s38_append_only_unstaged_attributes(root: Path) -> None:
    base_ledger(root)
    (root / ".gitattributes").write_text("DECISIONS.md -diff\n", encoding="utf-8")
    (root / "DECISIONS.md").write_text(
        "# DECISIONS\n\nwholesale rewrite\n", encoding="utf-8")
    git(root, "add", "DECISIONS.md")


def s39_bare_repo_git_failure(root: Path) -> None:
    git(root, "init", "--bare", "-q", ".")


def s40_missing_index(root: Path) -> None:
    base_ledger(root)
    os.unlink(root / ".git" / "index")


def s41_append_only_middle_insertion(root: Path) -> None:
    base_ledger(root)
    path = root / "DECISIONS.md"
    path.write_text(path.read_text().replace(
        "# DECISIONS\n\n", "# DECISIONS\ninserted context\n\n"), encoding="utf-8")
    git(root, "add", "DECISIONS.md")


def s42_rename_within_same_rule(root: Path) -> None:
    base_ledger(root)
    (root / "docs").mkdir()
    git(root, "mv", "DECISIONS.md", "docs/DECISIONS.md")


SCENARIOS = {
    name: fn
    for name, fn in sorted(globals().items())
    if name.startswith("s") and callable(fn)
}


def no_git() -> bool:
    return shutil.which("git") is None
