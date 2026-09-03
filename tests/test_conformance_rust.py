"""Rust↔Python staged-floor conformance (T-0021, licensed by D-0014).

For every scenario in conformance_scenarios: build the repo state, then run
BOTH kernels and assert byte-identical verdicts — exit code AND stdout.
Python is normative; any divergence fails CI, which is the only reason the
Rust duplicate (crates/statutor) may exist.

Binary resolution: $STATUTOR_STAGED_BIN if set, else `cargo build --release`
into a session-isolated target directory. Skips when neither exists, mirroring
the suite's other optional-dependency skips.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import conformance_scenarios as cs

REPO_ROOT = Path(__file__).resolve().parents[1]
KERNEL = REPO_ROOT / "core" / "statutor_core.py"
CRATE = REPO_ROOT / "crates" / "statutor"

NO_GIT = cs.no_git()
git_required = pytest.mark.skipif(NO_GIT, reason="git not available")

# Semantic expectations for the lifecycle/failure cases repaired by T-0025.
# Differential parity is necessary but insufficient: these assertions prevent
# both implementations from agreeing on the old permissive behavior.
EXPECTED = {
    "s05_rm_whole_file": (1, "record cannot be deleted"),
    "s10_archive_direct_add": (1, "direct additions to the archive are denied"),
    "s11_rename_into_archive": (0, ""),
    "s12_rename_out_of_archive": (1, "frozen"),
    "s23_not_a_git_repo": (1, "git rev-parse --is-inside-work-tree failed"),
    "s27_rename_r100_exact": (1, "record cannot move"),
    "s30_malformed_statutor_yaml_fails_closed": (1, "invalid or unsupported Statutor policy"),
    "s31_delete_agents_record": (1, "record cannot be deleted"),
    "s32_rename_agents_out": (1, "record cannot move"),
    "s33_delete_handoff_record": (1, "record cannot be deleted"),
    "s34_rename_handoff_out": (1, "record cannot move"),
    "s35_rename_decisions_out": (1, "record cannot move"),
    "s36_delete_tasks_record": (1, "record cannot be deleted"),
    "s37_append_only_binary_rewrite": (1, "append-only"),
    "s38_append_only_unstaged_attributes": (1, "append-only"),
    "s39_bare_repo_git_failure": (1, "reported no worktree"),
    "s40_missing_index": (1, "record cannot be deleted"),
    "s41_append_only_middle_insertion": (0, ""),
    "s42_rename_within_same_rule": (0, ""),
    "s43_quoted_cap_exact_trailing_lf": (0, ""),
    "s44_quoted_cap_over_trailing_lf": (1, "41 lines (cap 40)"),
    "s45_unstaged_policy_weakening_ignored": (1, "append-only"),
    "s46_costaged_policy_weakening_cannot_self_authorize": (1, "trust-root change requires"),
    "s47_policy_change_requires_receipt": (1, "missing, stale, or unsafe receipt"),
    "s48_malformed_candidate_policy_fails_closed": (1, "invalid or unsupported Statutor policy"),
    "s49_managed_claude_bridge_change_needs_receipt": (1, "CLAUDE.md"),
    "s50_unmanaged_claude_change_allowed": (0, ""),
    "s51_bootstrap_candidate_policy_judges_transaction": (1, "NOTES.md: append-only"),
    "s52_exact_tree_receipt_authorizes_policy_change": (0, ""),
    "s53_state_checkbox_detail_reorder_add_allowed": (0, ""),
    "s54_state_existing_id_removal_denied": (1, "T-0001"),
    "s55_state_id_rewrite_denied": (1, "T-0001"),
    "s56_state_duplicate_id_denied": (1, "duplicate state task ID T-0001"),
    "s57_state_malformed_entry_denied": (1, "state line 1 must be"),
    "s58_state_new_id_must_advance": (1, "greater than existing maximum T-0001"),
    "s59_state_binary_denied": (1, "state content must be valid UTF-8"),
    "s60_tmp_swap_onto_policy_denied": (1, "missing, stale, or unsafe receipt"),
}


def _cargo_available() -> bool:
    return shutil.which("cargo") is not None


def _staged_artifact(cargo_stdout: str) -> Path:
    artifacts = []
    for line in cargo_stdout.splitlines():
        message = json.loads(line)
        target = message.get("target", {})
        if (message.get("reason") == "compiler-artifact"
                and target.get("name") == "statutor-staged"
                and "bin" in target.get("kind", [])
                and message.get("executable")):
            artifacts.append(Path(message["executable"]))
    if len(artifacts) != 1:
        raise ValueError(
            f"cargo reported {len(artifacts)} statutor-staged executables")
    return artifacts[0]


@pytest.fixture(scope="session")
def staged_bin(tmp_path_factory: pytest.TempPathFactory) -> Path:
    env_bin = os.environ.get("STATUTOR_STAGED_BIN")
    if env_bin:
        p = Path(env_bin)
        if not p.exists():
            pytest.fail(f"STATUTOR_STAGED_BIN points at missing binary: {env_bin}")
        return p
    if not _cargo_available():
        pytest.skip("no STATUTOR_STAGED_BIN and cargo unavailable")
    target_dir = tmp_path_factory.mktemp("statutor-cargo-target")
    build_env = {**os.environ, "CARGO_TARGET_DIR": str(target_dir)}
    build = subprocess.run(
        ["cargo", "build", "--locked", "--release",
         "--message-format=json-render-diagnostics", "--manifest-path",
         str(CRATE / "Cargo.toml")],
        env=build_env, capture_output=True, text=True)
    if build.returncode != 0:
        pytest.fail(f"cargo build failed:\n{build.stderr}")
    try:
        bin_path = _staged_artifact(build.stdout)
    except ValueError as exc:
        pytest.fail(str(exc))
    assert bin_path.exists(), "cargo reported success but binary is absent"
    return bin_path


def test_staged_artifact_uses_cargo_reported_cross_target_path(
        tmp_path: Path) -> None:
    expected = tmp_path / "aarch64-unknown-linux-gnu" / "release" / "statutor-staged"
    cargo_stdout = "\n".join([
        json.dumps({
            "reason": "compiler-artifact",
            "target": {"name": "statutor", "kind": ["lib"]},
            "executable": None,
        }),
        json.dumps({
            "reason": "compiler-artifact",
            "target": {"name": "statutor-staged", "kind": ["bin"]},
            "executable": str(expected),
        }),
    ])
    assert _staged_artifact(cargo_stdout) == expected


def _run_kernel(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(KERNEL), "staged", str(repo)],
                          env=cs.GIT_ENV, capture_output=True, text=True)


def _run_rust(bin_path: Path, repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(bin_path), str(repo)],
                          env=cs.GIT_ENV, capture_output=True, text=True)


def _scenario_ids() -> list[str]:
    return sorted(cs.SCENARIOS)


@git_required
@pytest.mark.parametrize("name", _scenario_ids())
def test_rust_matches_python(tmp_path: Path, name: str, staged_bin: Path) -> None:
    repo = tmp_path / name
    repo.mkdir()
    cs.SCENARIOS[name](repo)

    py = _run_kernel(repo)
    rs = _run_rust(staged_bin, repo)

    assert py.returncode == rs.returncode, (
        f"{name}: exit codes diverge (python={py.returncode} rust={rs.returncode})\n"
        f"python stdout:\n{py.stdout}\nrust stdout:\n{rs.stdout}")
    assert py.stdout == rs.stdout, (
        f"{name}: stdout diverges\npython:\n{py.stdout!r}\nrust:\n{rs.stdout!r}")

    if name in EXPECTED:
        expected_code, fragment = EXPECTED[name]
        assert py.returncode == expected_code, (
            f"{name}: expected exit {expected_code}, got {py.returncode}\n{py.stdout}")
        if fragment:
            assert fragment in py.stdout, (
                f"{name}: expected {fragment!r} in stdout\n{py.stdout}")
        else:
            assert py.stdout == "", f"{name}: expected clean stdout\n{py.stdout}"


@git_required
def test_colored_gitconfig_diverges_nothing(tmp_path: Path, staged_bin: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """The post-fix kernels pin color.ui=false themselves, so a hostile user
    gitconfig must not change EITHER implementation's verdict."""
    repo = tmp_path / "colored"
    repo.mkdir()
    cs.s03_delete_last_line(repo)
    colorful = tmp_path / "colorful.gitconfig"
    colorful.write_text("[color]\n\tui = always\n", encoding="utf-8")
    env = {**cs.GIT_ENV, "GIT_CONFIG_GLOBAL": str(colorful)}

    py = subprocess.run([sys.executable, str(KERNEL), "staged", str(repo)],
                        env=env, capture_output=True, text=True)
    rs = subprocess.run([str(staged_bin), str(repo)],
                        env=env, capture_output=True, text=True)

    assert py.returncode == rs.returncode == 1
    assert py.stdout == rs.stdout != ""
