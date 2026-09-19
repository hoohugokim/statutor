"""T-0043 / D-0024: opt-out init profiles.

Profiles add conventional *directories* on top of the governed files and are
selected by `--type` > `STATUTOR_INIT_TYPE` > marker detection > `min`. The
hard guarantees under test: the `min` fallback is byte-identical to the
pre-v0.6 `init`, every create is additive and idempotent, no profile writes
policy or content, and definitions stay embedded in the kernel.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import pytest

import statutor_core

REPO_ROOT = Path(__file__).resolve().parents[1]
KERNEL = REPO_ROOT / "core" / "statutor_core.py"
ENV = statutor_core.INIT_TYPE_ENV

LEGACY_FRESH = ([f"write {name}" for name in statutor_core.TEMPLATES]
                + ["write CLAUDE.md (@AGENTS.md import)"])
LEGACY_SECOND = [f"skip  {name} (exists)" for name in statutor_core.TEMPLATES]
GOVERNED = set(statutor_core.TEMPLATES) | {"CLAUDE.md"}
SKELETON = {"plans", "plans/archive", "notes"}
DETECTABLE = [name for name in statutor_core.INIT_PROFILES
              if statutor_core.INIT_PROFILES[name]["markers"]]


def tree(root: Path) -> set[str]:
    """Every path under `root`, POSIX-relative, files and directories alike."""
    found: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        for entry in dirnames + filenames:
            found.add((rel / entry).as_posix())
    return found


def expected_tree(profile: str) -> set[str]:
    dirs = set(statutor_core.INIT_PROFILES[profile]["dirs"])
    return GOVERNED | dirs | (set() if profile == "none" else SKELETON)


def run_cli(args: list[str], cwd: Path, env_extra: dict[str, str] | None = None
            ) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if key != ENV}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(KERNEL), "init", *args], cwd=str(cwd),
                          capture_output=True, text=True, env=env)


# --------------------------------------------------------------------------
# the byte-identical `min` guarantee
# --------------------------------------------------------------------------

def test_fallback_min_is_byte_identical_to_legacy_init(tmp_path, capsys):
    assert statutor_core.run_init(str(tmp_path)) == 0
    assert capsys.readouterr().out.splitlines() == LEGACY_FRESH
    assert tree(tmp_path) == GOVERNED | SKELETON
    assert statutor_core.run_init(str(tmp_path)) == 0
    assert capsys.readouterr().out.splitlines() == LEGACY_SECOND


def test_env_is_not_consulted_in_process(tmp_path, monkeypatch, capsys):
    """Library callers stay deterministic: only the CLI reads the process env."""
    monkeypatch.setenv(ENV, "none")
    statutor_core.run_init(str(tmp_path))
    assert capsys.readouterr().out.splitlines() == LEGACY_FRESH
    assert tree(tmp_path) == GOVERNED | SKELETON


def test_resolve_touches_nothing_on_disk(tmp_path):
    target = tmp_path / "absent"
    assert statutor_core.resolve_init_profile(str(target)) == ("min", "fallback")
    assert not target.exists()


# --------------------------------------------------------------------------
# profile matrix: exact trees and exact output
# --------------------------------------------------------------------------

@pytest.mark.parametrize("profile", list(statutor_core.INIT_PROFILES))
def test_explicit_type_creates_exact_tree(tmp_path, capsys, profile):
    assert statutor_core.run_init(str(tmp_path), profile=profile) == 0
    out = capsys.readouterr().out.splitlines()
    dirs = statutor_core.INIT_PROFILES[profile]["dirs"]
    assert out == ([f"profile {profile} (--type)"] + LEGACY_FRESH
                   + [f"mkdir {rel}/" for rel in dirs])
    assert tree(tmp_path) == expected_tree(profile)


@pytest.mark.parametrize("profile", DETECTABLE)
def test_each_marker_detects_its_profile(tmp_path, capsys, profile):
    for marker in statutor_core.INIT_PROFILES[profile]["markers"]:
        root = tmp_path / marker.replace(".", "_")
        root.mkdir()
        marker_is_dir = marker in statutor_core.INIT_PROFILES[profile]["dirs"]
        (root / marker).mkdir() if marker_is_dir else (root / marker).write_text("x")
        assert statutor_core.run_init(str(root)) == 0
        out = capsys.readouterr().out.splitlines()
        tail = [f"skip  {rel}/ (exists)" if rel == marker else f"mkdir {rel}/"
                for rel in statutor_core.INIT_PROFILES[profile]["dirs"]]
        assert out == [f"profile {profile} (detected {marker})"] + LEGACY_FRESH + tail
        assert tree(root) == expected_tree(profile) | {marker}


@pytest.mark.parametrize("markers, winner, reported", [
    (["pyproject.toml", "Cargo.toml", "package.json", "mkdocs.yml", "docs"],
     "python", "pyproject.toml"),
    (["setup.cfg", "Cargo.toml"], "python", "setup.cfg"),
    (["Cargo.toml", "package.json", "mkdocs.yml"], "rust", "Cargo.toml"),
    (["package.json", "_quarto.yml"], "node", "package.json"),
    (["_quarto.yml"], "docs", "_quarto.yml"),
    (["docs"], "docs", "docs"),
])
def test_detection_order_resolves_conflicts(tmp_path, markers, winner, reported):
    for marker in markers:
        (tmp_path / marker).mkdir() if marker == "docs" else (tmp_path / marker).write_text("x")
    assert statutor_core.resolve_init_profile(str(tmp_path)) == (winner, f"detected {reported}")


def test_detection_looks_only_at_the_target(tmp_path):
    (tmp_path / "pyproject.toml").write_text("x")
    child = tmp_path / "child"
    child.mkdir()
    assert statutor_core.resolve_init_profile(str(child)) == ("min", "fallback")


# --------------------------------------------------------------------------
# opt-out precedence
# --------------------------------------------------------------------------

def test_type_none_ignores_markers_and_creates_no_directories(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text("x")
    assert statutor_core.run_init(str(tmp_path), profile="none") == 0
    assert capsys.readouterr().out.splitlines() == ["profile none (--type)"] + LEGACY_FRESH
    assert tree(tmp_path) == GOVERNED | {"pyproject.toml"}


def test_env_selects_profile(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text("x")
    assert statutor_core.run_init(str(tmp_path), env={ENV: "node"}) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"profile node ({ENV})"
    assert tree(tmp_path) == expected_tree("node") | {"pyproject.toml"}


def test_flag_overrides_env(tmp_path, capsys):
    assert statutor_core.run_init(str(tmp_path), profile="docs", env={ENV: "rust"}) == 0
    assert capsys.readouterr().out.splitlines()[0] == "profile docs (--type)"
    assert tree(tmp_path) == expected_tree("docs")


def test_blank_env_value_counts_as_unset(tmp_path, capsys):
    (tmp_path / "Cargo.toml").write_text("x")
    assert statutor_core.run_init(str(tmp_path), env={ENV: "   "}) == 0
    assert capsys.readouterr().out.splitlines()[0] == "profile rust (detected Cargo.toml)"


def test_names_are_trimmed_and_case_insensitive(tmp_path, capsys):
    assert statutor_core.run_init(str(tmp_path), profile=" Rust ") == 0
    assert capsys.readouterr().out.splitlines()[0] == "profile rust (--type)"
    assert (tmp_path / "tests").is_dir()


@pytest.mark.parametrize("kwargs, source", [
    ({"profile": "bogus"}, "--type"),
    ({"profile": ""}, "--type"),
    ({"env": {ENV: "bogus"}}, ENV),
])
def test_unknown_profile_exits_64_before_any_write(tmp_path, capsys, kwargs, source):
    assert statutor_core.run_init(str(tmp_path), **kwargs) == 64
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"from {source}" in captured.err
    assert "choose one of none, min, python, rust, node, docs" in captured.err
    assert tree(tmp_path) == set()


# --------------------------------------------------------------------------
# additive, idempotent, never adopting
# --------------------------------------------------------------------------

def test_second_run_is_all_skips_and_preserves_bytes(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text("x")
    statutor_core.run_init(str(tmp_path))
    before = {rel: (tmp_path / rel).read_bytes() for rel in GOVERNED}
    capsys.readouterr()
    assert statutor_core.run_init(str(tmp_path)) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == (["profile python (detected pyproject.toml)"] + LEGACY_SECOND
                   + ["skip  tests/ (exists)"])
    assert {rel: (tmp_path / rel).read_bytes() for rel in GOVERNED} == before
    assert tree(tmp_path) == expected_tree("python") | {"pyproject.toml"}


def test_present_file_where_profile_dir_would_go_is_left_alone(tmp_path, capsys):
    (tmp_path / "tests").write_text("keep me\n")
    assert statutor_core.run_init(str(tmp_path), profile="python") == 0
    assert capsys.readouterr().out.splitlines()[-1] == "skip  tests/ (exists)"
    assert (tmp_path / "tests").is_file()
    assert (tmp_path / "tests").read_text() == "keep me\n"


def test_dangling_symlink_where_profile_dir_would_go_is_left_alone(tmp_path, capsys):
    os.symlink("nowhere", tmp_path / "test")
    assert statutor_core.run_init(str(tmp_path), profile="node") == 0
    assert capsys.readouterr().out.splitlines()[-1] == "skip  test/ (exists)"
    assert os.path.islink(tmp_path / "test")
    assert os.readlink(tmp_path / "test") == "nowhere"


def test_missing_target_is_created_for_every_profile(tmp_path):
    for profile in statutor_core.INIT_PROFILES:
        target = tmp_path / profile / "nested"
        assert statutor_core.run_init(str(target), profile=profile) == 0
        assert tree(target) == expected_tree(profile)


# --------------------------------------------------------------------------
# scaffold-only guarantee and embedded definitions
# --------------------------------------------------------------------------

def test_profiles_are_embedded_directory_only_definitions():
    assert not (REPO_ROOT / "profiles").exists()
    profiles = statutor_core.INIT_PROFILES
    assert set(profiles) == {"none", "min", "python", "rust", "node", "docs"}
    assert set(statutor_core.INIT_DETECT_ORDER) == set(DETECTABLE)
    assert not set(statutor_core.INIT_DETECT_ORDER) & {"none", "min"}
    assert profiles["none"] == {"dirs": (), "markers": ()}
    assert profiles["min"] == {"dirs": (), "markers": ()}
    reserved = GOVERNED | set(statutor_core.INIT_SKELETON_DIRS)
    for name, definition in profiles.items():
        assert set(definition) == {"dirs", "markers"}
        for rel in definition["dirs"]:
            assert rel and not rel.startswith(("/", ".", "-")) and ".." not in rel
            assert not rel.endswith((".md", ".yaml", ".yml", ".json", ".toml", ".py"))
            assert rel not in reserved


@pytest.mark.parametrize("profile", list(statutor_core.INIT_PROFILES))
def test_every_profile_writes_identical_templates_and_default_policy(tmp_path, profile):
    statutor_core.run_init(str(tmp_path), profile=profile)
    for name, body in statutor_core.TEMPLATES.items():
        assert (tmp_path / name).read_text(encoding="utf-8") == body
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    parsed = statutor_core.parse_policy((tmp_path / ".statutor.yaml").read_bytes())
    assert parsed == statutor_core.DEFAULT_POLICY


def test_release_gate_smoke_ignores_the_operator_init_preference():
    source = (REPO_ROOT / "scripts" / "release_gate.py").read_text(encoding="utf-8")
    assert f'smoke_env.pop("{ENV}", None)' in source


# --------------------------------------------------------------------------
# CLI surface
# --------------------------------------------------------------------------

@pytest.mark.parametrize("args", [["--type", "node", "{dir}"], ["{dir}", "--type=node"]])
def test_cli_accepts_both_flag_forms(tmp_path, args):
    target = tmp_path / "proj"
    result = run_cli([arg.format(dir=str(target)) for arg in args], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "profile node (--type)"
    assert tree(target) == expected_tree("node")


def test_cli_reads_env_and_flag_still_wins(tmp_path):
    quiet = tmp_path / "quiet"
    result = run_cli([str(quiet)], cwd=tmp_path, env_extra={ENV: "none"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == f"profile none ({ENV})"
    assert tree(quiet) == GOVERNED
    loud = tmp_path / "loud"
    result = run_cli([str(loud), "--type", "min"], cwd=tmp_path, env_extra={ENV: "none"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "profile min (--type)"
    assert tree(loud) == GOVERNED | SKELETON


def test_cli_default_directory_is_cwd_with_detection(tmp_path):
    (tmp_path / "Cargo.toml").write_text("x")
    result = run_cli([], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "profile rust (detected Cargo.toml)"
    assert (tmp_path / "tests").is_dir()


@pytest.mark.parametrize("args, message", [
    (["--type"], "missing value for --type"),
    (["a", "b"], "unexpected argument: b"),
    (["--bogus"], "unexpected argument: --bogus"),
    (["--type", "bogus"], "unknown init profile 'bogus' from --type"),
])
def test_cli_usage_errors_exit_64_and_write_nothing(tmp_path, args, message):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 64
    assert message in result.stderr
    assert "usage: statutor init [DIR] [--type none|min|python|rust|node|docs]" in result.stderr
    assert result.stdout == ""
    assert tree(tmp_path) == set()


def test_cli_help_prints_usage_and_writes_nothing(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout.startswith("usage: statutor init [DIR] [--type ")
    assert f"(env: {ENV}=NAME)" in result.stdout
    assert tree(tmp_path) == set()


def test_cli_invalid_env_exits_64_and_writes_nothing(tmp_path):
    result = run_cli([str(tmp_path)], cwd=tmp_path, env_extra={ENV: "nope"})
    assert result.returncode == 64
    assert f"unknown init profile 'nope' from {ENV}" in result.stderr
    assert tree(tmp_path) == set()
