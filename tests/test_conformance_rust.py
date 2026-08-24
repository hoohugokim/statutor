"""Rust↔Python staged-floor conformance (T-0021, licensed by D-0014).

For every scenario in conformance_scenarios: build the repo state, then run
BOTH kernels and assert byte-identical verdicts — exit code AND stdout.
Python is normative; any divergence fails CI, which is the only reason the
Rust duplicate (crates/statutor) may exist.

Binary resolution: $STATUTOR_STAGED_BIN if set, else `cargo build --release`
in crates/statutor. Skips when neither exists, mirroring the suite's other
optional-dependency skips.
"""

from __future__ import annotations

import importlib.util
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

# Scenarios whose whole point is a .statutor.yaml the PYTHON side must parse:
# without PyYAML the Python kernel silently falls back to embedded defaults
# while Rust applies the file — an environmental false divergence, not a
# behavioral one. They run in CI's pyyaml leg.
PYAML_AVAILABLE = importlib.util.find_spec("yaml") is not None
NEEDS_PYAML = {"s25_statutor_yaml_governed_empty", "s29_statutor_yaml_custom_names"}


def _cargo_available() -> bool:
    return shutil.which("cargo") is not None


@pytest.fixture(scope="session")
def staged_bin() -> Path:
    env_bin = os.environ.get("STATUTOR_STAGED_BIN")
    if env_bin:
        p = Path(env_bin)
        if not p.exists():
            pytest.fail(f"STATUTOR_STAGED_BIN points at missing binary: {env_bin}")
        return p
    if not _cargo_available():
        pytest.skip("no STATUTOR_STAGED_BIN and cargo unavailable")
    build = subprocess.run(
        ["cargo", "build", "-q", "--release", "--manifest-path",
         str(CRATE / "Cargo.toml")],
        capture_output=True, text=True)
    if build.returncode != 0:
        pytest.fail(f"cargo build failed:\n{build.stderr}")
    bin_path = CRATE / "target" / "release" / "statutor-staged"
    assert bin_path.exists(), "cargo reported success but binary is absent"
    return bin_path


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
    if name in NEEDS_PYAML and not PYAML_AVAILABLE:
        pytest.skip("scenario needs a PyYAML-capable python kernel")
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
