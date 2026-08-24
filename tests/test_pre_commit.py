"""Tests for adapters/git/pre-commit — the copyable git-floor hook script (T-0012).

The script's contract:
  * `statutor` on PATH  → exec `statutor staged <toplevel>` verbatim
    (exit codes propagate: 0 clean, 1 violation).
  * `statutor` missing  → FAIL CLOSED (exit 1, instructions on stderr).
    The previous fallback (`python3 .statutor/statutor_core.py staged`) pointed
    at a kernel copy that nothing ever created; vendoring would fork the
    single-kernel source of truth, so the branch was dropped.

No conftest.py: this module bootstraps its own sys.path like its siblings.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "adapters" / "git" / "pre-commit"

NO_GIT = shutil.which("git") is None
git_required = pytest.mark.skipif(NO_GIT, reason="git not available")

GIT_ENV = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}

SHELL = shutil.which("sh") or "/bin/sh"


def git(cwd, *args) -> None:
    subprocess.run(["git", "-c", "user.email=statutor@test", "-c", "user.name=statutor test",
                    *args], cwd=str(cwd), env=GIT_ENV, capture_output=True, text=True, check=True)


def run_script(repo: Path, statutor_on_path: bool = True) -> subprocess.CompletedProcess:
    """Run the hook against a hermetic PATH containing only git plus,
    optionally, a `statutor` shim that execs the in-repo kernel — so the
    pass-through branch is exercised even on machines without a global
    `pipx install statutor`, and the fail-closed branch sees a PATH where
    the CLI is genuinely absent."""
    fake_bin = repo / ".fakebin"
    fake_bin.mkdir(exist_ok=True)
    git_exe = shutil.which("git")
    if git_exe and not (fake_bin / "git").exists():
        os.symlink(git_exe, fake_bin / "git")
    if statutor_on_path and not (fake_bin / "statutor").exists():
        shim = fake_bin / "statutor"
        shim.write_text(
            "#!/bin/sh\n"
            f'exec "{sys.executable}" "{REPO_ROOT / "core" / "statutor_core.py"}" "$@"\n',
            encoding="utf-8")
        shim.chmod(0o755)
    return subprocess.run([SHELL, str(SCRIPT)], cwd=str(repo),
                          env={**GIT_ENV, "PATH": str(fake_bin)},
                          capture_output=True, text=True)


@pytest.fixture
def ledger_repo(tmp_path: Path) -> Path:
    assert NO_GIT is False
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "DECISIONS.md").write_text("# DECISIONS\n\n## D-0001\nfirst\n", encoding="utf-8")
    (tmp_path / "HANDOFF.md").write_text(
        "# HANDOFF\nlast_verified: 2026-08-24 by `pytest`\n\n## Goal\ng\n\n"
        "## Last verified state\ns\n\n## Next action\nn\n\n## Gotchas\ngo\n\n"
        "## Do not touch\nd\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# AGENTS\nshort\n", encoding="utf-8")
    (tmp_path / "TASKS.md").write_text("- [ ] T-0001 one\n", encoding="utf-8")
    (tmp_path / "plans" / "archive").mkdir(parents=True)
    (tmp_path / "plans" / "archive" / "a1.md").write_text("archived\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init ledger")
    return tmp_path


@git_required
def test_clean_index_passes(ledger_repo):
    result = run_script(ledger_repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@git_required
def test_append_only_violation_denied(ledger_repo):
    path = ledger_repo / "DECISIONS.md"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(lines[:-1]), encoding="utf-8")
    git(ledger_repo, "add", "DECISIONS.md")
    result = run_script(ledger_repo)
    assert result.returncode == 1
    assert "append-only" in result.stdout


@git_required
def test_frozen_departure_denied(ledger_repo):
    git(ledger_repo, "rm", "-q", "plans/archive/a1.md")
    result = run_script(ledger_repo)
    assert result.returncode == 1
    assert "frozen" in result.stdout


@git_required
def test_missing_cli_fails_closed(ledger_repo):
    """No 'statutor' on PATH must exit 1 with install guidance — never a
    silent pass (that would defeat the universal floor) and never a
    traceback from a half-vendored kernel path."""
    result = run_script(ledger_repo, statutor_on_path=False)
    assert result.returncode == 1
    assert "not on PATH" in result.stderr
    assert "pipx install statutor" in result.stderr
