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
    "s61_receipt_omitting_null_optional_oids_authorizes": (0, ""),
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


@git_required
@pytest.mark.parametrize("policy", [
    b"{governed: []}\n",
    b"governed: [{pattern: NOTES.md, policy: frozen}]\n",
    b"governed: []\n---\ngoverned: []\n",
    b"governed: &rules []\n",
    b"governed: []\ngoverned: []\n",
    b"governed:\n  - pattern: NOTES.md\n    policy: frozen\n    policy: state\n",
    b"governed:\n  - pattern: NOTES.md\n    policy: []\n",
    b"governed:\n  - pattern: NOTES.md\n    policy: frozen\n    required_sections: [one]\n",
    b"governed:\n  - pattern: NOTES.md\n    policy: frozen\n    max_lines: 0x10\n",
    b"governed:\n  - pattern: NOTES.md\n    policy: frozen\n    max_lines: 1_000\n",
    b"governed:\n  - pattern: NOTES.md\n    policy: frozen\n    max_lines: true\n",
    b"governed:\n  - pattern: NOTES.md\n    policy: frozen\n    soft_max_lines: -1\n",
    b"governed:\n  - pattern: NOTES.md\n    policy: frozen\n    required_sections:\n      - \"\"\n",
    b"governed:\n  - pattern: \"\\x41\"\n    policy: frozen\n",
    b"governed:\n  - pattern: \"\\ud800\"\n    policy: frozen\n",
    b"governed:\n  - pattern: \"\\udfff\"\n    policy: frozen\n",
    b"governed:\n  - pattern: \xff.md\n    policy: frozen\n",
])
def test_unsupported_policy_syntax_fails_closed_in_both_floors(
        tmp_path: Path, staged_bin: Path, policy: bytes) -> None:
    cs.init_repo(tmp_path)
    (tmp_path / ".statutor.yaml").write_bytes(policy)
    cs.git(tmp_path, "add", ".statutor.yaml")
    py = _run_kernel(tmp_path)
    rs = _run_rust(staged_bin, tmp_path)
    assert py.returncode == rs.returncode == 1
    assert py.stdout == rs.stdout
    assert "invalid or unsupported Statutor policy" in py.stdout


@git_required
@pytest.mark.parametrize("policy", [
    "bash_guard: TRUE\ngoverned: []\n",
    "governed:\n  - pattern: 'true'\n    policy: frozen\n",
    "governed:\n  - pattern: 'a''b.md'\n    policy: frozen # data\n",
    'governed:\n  - pattern: "a\\u0023b.md"\n    policy: frozen\n',
    'governed:\n  - pattern: NOTES.md\n    policy: constitution\n    max_lines: "01"\n',
    'governed:\n  - pattern: NOTES.md\n    policy: constitution\n    max_lines: +0001\n',
    "governed:\n  - pattern: NOTES.md\n    policy: constitution\n    max_lines: 999999999999999999999999\n",
    "governed:\n  - pattern: NOTES.md\n    policy: constitution\n    max_lines: '１２'\n",
    'governed:\n  - pattern: "\\ud83d\\ude00.md"\n    policy: frozen\n',
])
def test_supported_policy_scalars_match_canonical_parser(
        tmp_path: Path, staged_bin: Path, policy: str) -> None:
    cs.init_repo(tmp_path)
    (tmp_path / ".statutor.yaml").write_text(policy, encoding="utf-8")
    cs.git(tmp_path, "add", ".statutor.yaml")
    py = _run_kernel(tmp_path)
    rs = _run_rust(staged_bin, tmp_path)
    assert py.returncode == rs.returncode == 0, (py.stdout, rs.stdout)
    assert py.stdout == rs.stdout == ""


@git_required
@pytest.mark.parametrize("name,mutation", [
    (".statutor.yaml", "symlink"),
    ("CLAUDE.md", "symlink"),
    (".statutor.yaml", "executable"),
    ("CLAUDE.md", "executable"),
])
def test_trust_root_mode_changes_require_exact_tree_approval(
        tmp_path: Path, staged_bin: Path, name: str, mutation: str) -> None:
    cs.init_repo(tmp_path)
    (tmp_path / ".statutor.yaml").write_text("governed: []\n")
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md")
    cs.git(tmp_path, "add", "-A")
    cs.git(tmp_path, "commit", "-qm", "base")
    target = tmp_path / name
    if mutation == "symlink":
        body = target.read_text()
        target.unlink()
        target.symlink_to(body)
        cs.git(tmp_path, "add", name)
    else:
        cs.git(tmp_path, "update-index", "--chmod=+x", name)
    py = _run_kernel(tmp_path)
    rs = _run_rust(staged_bin, tmp_path)
    assert py.returncode == rs.returncode == 1
    assert py.stdout == rs.stdout
    assert "trust-root change requires" in py.stdout
    tree = subprocess.check_output(["git", "write-tree"], cwd=tmp_path,
                                   env=cs.GIT_ENV, text=True).strip()
    approval = subprocess.run(
        [sys.executable, str(KERNEL), "trust", "approve", str(tmp_path),
         "--decision", "D-0015", "--reason", "mode transition regression",
         "--confirm-tree", tree], capture_output=True, text=True, env=cs.GIT_ENV)
    assert approval.returncode == 0, approval.stderr
    assert _run_kernel(tmp_path).returncode == _run_rust(staged_bin, tmp_path).returncode == 0


@git_required
def test_nested_floor_and_trust_approval_use_complete_git_transaction(
        tmp_path: Path, staged_bin: Path) -> None:
    cs.init_repo(tmp_path)
    policy = "governed:\n  - pattern: NOTES.md\n    policy: append_only\n"
    (tmp_path / ".statutor.yaml").write_text(policy)
    (tmp_path / "NOTES.md").write_text("original\n")
    nested = tmp_path / "src"
    nested.mkdir()
    cs.git(tmp_path, "add", "-A")
    cs.git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "NOTES.md").write_text("rewritten\n")
    cs.git(tmp_path, "add", "NOTES.md")
    for cwd in (tmp_path, nested):
        py = _run_kernel(cwd)
        rs = _run_rust(staged_bin, cwd)
        assert py.returncode == rs.returncode == 1
        assert py.stdout == rs.stdout
        assert "append-only" in py.stdout
    cs.git(tmp_path, "reset", "-q", "--hard")
    (tmp_path / ".statutor.yaml").write_text(policy + "\n")
    cs.git(tmp_path, "add", ".statutor.yaml")
    tree = subprocess.check_output(["git", "write-tree"], cwd=tmp_path,
                                   env=cs.GIT_ENV, text=True).strip()
    approval = subprocess.run(
        [sys.executable, str(KERNEL), "trust", "approve", "--decision", "D-0015",
         "--reason", "nested invocation", "--confirm-tree", tree], cwd=nested,
        env=cs.GIT_ENV, capture_output=True, text=True)
    assert approval.returncode == 0, approval.stderr
    assert _run_kernel(nested).returncode == _run_rust(staged_bin, nested).returncode == 0


@git_required
@pytest.mark.parametrize("pattern,name", [
    ("[^a].md", "a.md"), ("[]a].md", "a.md"),
    ("[!a].md", "b.md"), ("[a-b-c].md", "-.md"),
    ("[!a].md", "[.md"), ("*?.md", "*.md"),
    ("[b-a!].md", "a.md"),
])
def test_python_character_classes_protect_same_frozen_paths(
        tmp_path: Path, staged_bin: Path, pattern: str, name: str) -> None:
    cs.init_repo(tmp_path)
    (tmp_path / ".statutor.yaml").write_text(
        f"governed:\n  - pattern: '{pattern}'\n    policy: frozen\n")
    (tmp_path / name).write_text("original\n")
    cs.git(tmp_path, "add", "-A")
    cs.git(tmp_path, "commit", "-qm", "base")
    (tmp_path / name).write_text("changed\n")
    cs.git(tmp_path, "add", "--", name)
    py = _run_kernel(tmp_path)
    rs = _run_rust(staged_bin, tmp_path)
    assert py.returncode == rs.returncode == 1
    assert py.stdout == rs.stdout
    assert "frozen" in py.stdout


@git_required
@pytest.mark.parametrize("candidate", [
    "- [x] T-0001\tupdated\n",
    "- [ ] T-0001 one\n- [ ] T-0000 low\n- [ ] T-0000 different\n",
    "- [ ] T-0001 one\n- [ ] T-0000 low\n- [ ] T-00000 lower\n",
    "- [ ] T-0001 one\n- [ ] T-999999999999999999999999999999999999999 new\n",
    "- [ ] T-0001 one\r\n- [ ] T-bad malformed\r\n",
    "- [ ] T-0001 one\u2028- [ ] T-bad malformed\u2028",
])
def test_state_spacing_and_diagnostic_order_match_python(
        tmp_path: Path, staged_bin: Path, candidate: str) -> None:
    cs.base_ledger(tmp_path)
    (tmp_path / "TASKS.md").write_text(candidate)
    cs.git(tmp_path, "add", "TASKS.md")
    py = _run_kernel(tmp_path)
    for _ in range(5):
        rs = _run_rust(staged_bin, tmp_path)
        assert py.returncode == rs.returncode
        assert py.stdout == rs.stdout


@git_required
def test_pinned_unicode_16_decimal_blocks_match_rust(
        tmp_path: Path, staged_bin: Path) -> None:
    import statutor_core

    # D-0029 pins the grammar to this version, independently of Python's UCD:
    # https://www.unicode.org/Public/16.0.0/ucd/extracted/DerivedNumericType.txt
    starts = (
        0x30, 0x660, 0x6F0, 0x7C0, 0x966, 0x9E6, 0xA66, 0xAE6, 0xB66, 0xBE6,
        0xC66, 0xCE6, 0xD66, 0xDE6, 0xE50, 0xED0, 0xF20, 0x1040, 0x1090, 0x17E0,
        0x1810, 0x1946, 0x19D0, 0x1A80, 0x1A90, 0x1B50, 0x1BB0, 0x1C40, 0x1C50,
        0xA620, 0xA8D0, 0xA900, 0xA9D0, 0xA9F0, 0xAA50, 0xABF0, 0xFF10,
        0x104A0, 0x10D30, 0x10D40, 0x11066, 0x110F0, 0x11136, 0x111D0, 0x112F0,
        0x11450, 0x114D0, 0x11650, 0x116C0, 0x116D0, 0x116DA, 0x11730, 0x118E0,
        0x11950, 0x11BF0, 0x11C50, 0x11D50, 0x11DA0, 0x11F50, 0x16130, 0x16A60,
        0x16AC0, 0x16B50, 0x16D70, 0x1CCF0, 0x1D7CE, 0x1D7D8, 0x1D7E2, 0x1D7EC,
        0x1D7F6, 0x1E140, 0x1E2F0, 0x1E4F0, 0x1E5F1, 0x1E950, 0x1FBF0,
    )
    assert set(starts) == set(statutor_core._DECIMAL_STARTS)
    policy = "governed:\n" + "".join(
        f"  - pattern: note-{index}.md\n    policy: constitution\n"
        f"    max_lines: '{chr(start + 1)}{chr(start + 2)}'\n"
        for index, start in enumerate(starts))
    cs.init_repo(tmp_path)
    (tmp_path / ".statutor.yaml").write_text(policy)
    cs.git(tmp_path, "add", ".statutor.yaml")
    assert _run_kernel(tmp_path).returncode == _run_rust(staged_bin, tmp_path).returncode == 0
    cs.git(tmp_path, "reset", "-q", "--hard")
    (tmp_path / ".statutor.yaml").write_text(
        "governed:\n  - pattern: TASKS.md\n    policy: state\n")
    (tmp_path / "TASKS.md").write_text("".join(
        "- [ ] T-" + chr(start) * 3 + chr(start+1) + " detail\n"
        for start in starts))
    cs.git(tmp_path, "add", ".statutor.yaml", "TASKS.md")
    assert _run_kernel(tmp_path).returncode == _run_rust(staged_bin, tmp_path).returncode == 0


@git_required
@pytest.mark.parametrize("mode", ["cap", "task"])
def test_unicode_17_decimal_digits_remain_outside_pinned_grammar(
        tmp_path: Path, staged_bin: Path, mode: str) -> None:
    cs.init_repo(tmp_path)
    if mode == "cap":
        policy = ("governed:\n  - pattern: NOTE.md\n    policy: constitution\n"
                  "    max_lines: '\U00011de1\U00011de2'\n")
    else:
        policy = "governed:\n  - pattern: TASKS.md\n    policy: state\n"
        (tmp_path / "TASKS.md").write_text(
            "- [ ] T-\U00011de0\U00011de0\U00011de0\U00011de1 detail\n", encoding="utf-8")
    (tmp_path / ".statutor.yaml").write_text(policy, encoding="utf-8")
    cs.git(tmp_path, "add", "-A")
    py = _run_kernel(tmp_path)
    rs = _run_rust(staged_bin, tmp_path)
    assert py.returncode == rs.returncode == 1
    assert py.stdout == rs.stdout
    assert ("invalid or unsupported Statutor policy" if mode == "cap"
            else "state line 1 must be") in py.stdout


@git_required
def test_arbitrary_size_decimal_caps_and_state_ids_match(
        tmp_path: Path, staged_bin: Path) -> None:
    large = "9" * 5000
    cs.init_repo(tmp_path)
    (tmp_path / ".statutor.yaml").write_text(
        "governed:\n  - pattern: TASKS.md\n    policy: state\n"
        "  - pattern: NOTES.md\n    policy: constitution\n    max_lines: " + large + "\n")
    (tmp_path / "TASKS.md").write_text(f"- [ ] T-{large} first\n")
    cs.git(tmp_path, "add", "-A")
    assert _run_kernel(tmp_path).returncode == _run_rust(staged_bin, tmp_path).returncode == 0
    cs.git(tmp_path, "commit", "-qm", "large identities")
    (tmp_path / "TASKS.md").write_text(
        f"- [ ] T-{large} first\n- [ ] T-0000 invalid successor\n")
    cs.git(tmp_path, "add", "TASKS.md")
    py = _run_kernel(tmp_path)
    rs = _run_rust(staged_bin, tmp_path)
    assert py.returncode == rs.returncode == 1
    assert py.stdout == rs.stdout
    assert f"maximum T-{large}" in py.stdout


@git_required
@pytest.mark.skipif(os.name == "nt", reason="backslash is a separator on Windows")
def test_literal_backslash_filename_keeps_python_policy_matching(
        tmp_path: Path, staged_bin: Path) -> None:
    cs.init_repo(tmp_path)
    name = "docs\\NOTES.md"
    (tmp_path / ".statutor.yaml").write_text(
        f"governed:\n  - pattern: '{name}'\n    policy: frozen\n")
    (tmp_path / name).write_text("original\n")
    cs.git(tmp_path, "add", "-A")
    cs.git(tmp_path, "commit", "-qm", "literal path")
    (tmp_path / name).write_text("changed\n")
    cs.git(tmp_path, "add", "--", name)
    py = _run_kernel(tmp_path)
    rs = _run_rust(staged_bin, tmp_path)
    assert py.returncode == rs.returncode == 1
    assert py.stdout == rs.stdout
    assert "frozen" in py.stdout


def _rust_match_names(root: Path, rels: list[str]) -> dict[str, str]:
    """Ask the shipped Rust matcher which policy each relative path takes."""
    spec = root.parent / f"match-cases-{root.name}.txt"
    spec.write_text(str(root) + "\n" + "\n".join(rels) + "\n", encoding="utf-8")
    env = {**os.environ, "STATUTOR_MATCH_CASES": str(spec)}
    proc = subprocess.run(
        ["cargo", "test", "--lib", "--locked", "--manifest-path",
         str(CRATE / "Cargo.toml"),
         "tests::match_rule_case_variant_follows_directory_entry",
         "--", "--exact", "--nocapture"],
        env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    found: dict[str, str] = {}
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        if not line.startswith("STATUTOR_MATCH "):
            continue
        _, rel, policy = line.split(" ", 2)
        found[rel] = policy
    return found


def test_match_rule_case_variant_agrees_with_rust(tmp_path: Path) -> None:
    """Python and Rust agree on directory-entry case variants."""
    if not _cargo_available():
        pytest.skip("cargo unavailable")
    sys.path.insert(0, str(REPO_ROOT / "core"))
    import statutor_core

    root = tmp_path / "ledger"
    root.mkdir()
    (root / "AGENTS.md").write_text("short\n", encoding="utf-8")
    notes = root / "notes"
    notes.mkdir()
    (notes / "agents.md").write_text("other\n", encoding="utf-8")
    variant = root / "agents.md"
    if variant.exists() and os.path.samefile(root / "AGENTS.md", variant):
        want_variant = "constitution"
    else:
        variant.write_text("different\n", encoding="utf-8")
        assert not os.path.samefile(root / "AGENTS.md", variant)
        want_variant = "none"
    expected = {
        "AGENTS.md": "constitution",
        "agents.md": want_variant,
        "notes/agents.md": "none",
    }
    policy = statutor_core.DEFAULT_POLICY
    for rel, want in expected.items():
        rule = statutor_core._match_rule(rel, policy, root=str(root))
        got = rule["policy"] if rule else "none"
        assert got == want, rel
    assert _rust_match_names(root, list(expected)) == expected
