#!/usr/bin/env python3
"""Build and prove Statutor release artifacts without publishing them."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION_RE = re.compile(
    r'(?ms)^\[project\]\s*$.*?^version\s*=\s*"([^"]+)"\s*$')
CARGO_VERSION_RE = re.compile(
    r'(?ms)^\[package\]\s*$.*?^version\s*=\s*"([^"]+)"\s*$')


def _run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    expected: int = 0,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=cwd, env=env, text=True)
    if result.returncode != expected:
        raise RuntimeError(
            f"command returned {result.returncode}, expected {expected}: "
            f"{' '.join(command)}")
    return result


def _match_version(path: Path, pattern: re.Pattern[str]) -> str:
    match = pattern.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise RuntimeError(f"could not read version from {path}")
    return match.group(1)


def versions(root: Path = ROOT) -> dict[str, str]:
    python = _match_version(root / "pyproject.toml", PYTHON_VERSION_RE)
    plugin = json.loads(
        (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )["version"]
    npm = json.loads(
        (root / "adapters" / "opencode" / "package.json").read_text(
            encoding="utf-8")
    )["version"]
    cargo = _match_version(
        root / "crates" / "statutor" / "Cargo.toml", CARGO_VERSION_RE)
    cargo_lock = (root / "crates" / "statutor" / "Cargo.lock").read_text(
        encoding="utf-8")
    locked = re.search(
        r'(?ms)^\[\[package\]\]\nname = "statutor"\nversion = "([^"]+)"',
        cargo_lock,
    )
    if python != plugin:
        raise RuntimeError(
            f"Python {python} != Claude plugin {plugin}")
    if locked is None or locked.group(1) != cargo:
        raise RuntimeError(
            f"Cargo manifest {cargo} != lockfile "
            f"{locked.group(1) if locked else '<missing>'}")
    return {"python": python, "plugin": plugin, "npm": npm, "cargo": cargo}


def _check_tag(tag: str | None, python_version: str) -> None:
    if tag is None:
        return
    expected = f"v{python_version}"
    if tag != expected:
        raise RuntimeError(f"release tag {tag} != package version {expected}")


def _candidate_tree(destination: Path) -> None:
    unstaged = subprocess.run(["git", "diff", "--quiet"], cwd=ROOT)
    if unstaged.returncode == 1:
        raise RuntimeError("tracked worktree changes are not staged")
    if unstaged.returncode != 0:
        raise RuntimeError("git diff could not inspect the worktree")
    _run(["git", "diff", "--cached", "--check"])
    _run([
        "git",
        "checkout-index",
        "--all",
        f"--prefix={destination}{os.sep}",
    ])


def _safe_parts(name: str, expected_root: str) -> tuple[str, ...]:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise RuntimeError(f"unsafe archive path: {name}")
    if path.parts[0] != expected_root:
        raise RuntimeError(f"unexpected archive root: {name}")
    return path.parts


def _audit_sdist(path: Path, version: str) -> None:
    prefix = f"statutor-{version}"
    expected = {
        "LICENSE",
        "MANIFEST.in",
        "PKG-INFO",
        "README.md",
        "pyproject.toml",
        "setup.cfg",
        "core/statutor.egg-info/PKG-INFO",
        "core/statutor.egg-info/SOURCES.txt",
        "core/statutor.egg-info/dependency_links.txt",
        "core/statutor.egg-info/entry_points.txt",
        "core/statutor.egg-info/top_level.txt",
        "core/statutor_core.py",
        "core/statutor_doctor.py",
        "core/statutor_global.py",
        "core/statutor_global_cli.py",
        "core/statutor_global_status.py",
        "core/statutor_skills.py",
    }
    seen: set[str] = set()
    private_markers = (b"/Users/", b"/home/", b"C:\\Users\\")
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            parts = _safe_parts(member.name, prefix)
            if member.isdir():
                continue
            if not member.isfile() or member.mode & 0o111:
                raise RuntimeError(f"unsafe sdist member: {member.name}")
            relative = PurePosixPath(*parts[1:]).as_posix()
            if relative in seen:
                raise RuntimeError(f"duplicate sdist member: {relative}")
            seen.add(relative)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"could not read sdist member: {relative}")
            content = extracted.read()
            content.decode("utf-8")
            if any(marker in content for marker in private_markers):
                raise RuntimeError(f"private path in sdist member: {relative}")
    if seen != expected:
        raise RuntimeError(
            f"sdist payload mismatch; missing={sorted(expected - seen)}, "
            f"extra={sorted(seen - expected)}")


def _audit_wheel(path: Path, version: str) -> None:
    dist = f"statutor-{version}.dist-info"
    expected = {
        "statutor_core.py",
        "statutor_doctor.py",
        "statutor_global.py",
        "statutor_global_cli.py",
        "statutor_global_status.py",
        "statutor_skills.py",
        f"{dist}/METADATA",
        f"{dist}/RECORD",
        f"{dist}/WHEEL",
        f"{dist}/entry_points.txt",
        f"{dist}/licenses/LICENSE",
        f"{dist}/top_level.txt",
    }
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if len(names) != len(archive.namelist()) or names != expected:
            raise RuntimeError(
                f"wheel payload mismatch; missing={sorted(expected - names)}, "
                f"extra={sorted(names - expected)}")
        for info in archive.infolist():
            _safe_parts(f"wheel/{info.filename}", "wheel")
            mode = (info.external_attr >> 16) & 0o777
            if mode & 0o111:
                raise RuntimeError(f"executable wheel member: {info.filename}")
            archive.read(info).decode("utf-8")
        metadata = archive.read(f"{dist}/METADATA").decode("utf-8")
        if f"Version: {version}\n" not in metadata:
            raise RuntimeError("wheel METADATA version mismatch")


def _smoke_wheel(wheel: Path, scratch: Path) -> None:
    site = scratch / "site"
    _run([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--no-index",
        "--target",
        str(site),
        str(wheel),
    ])
    bindir = site / ("Scripts" if os.name == "nt" else "bin")
    statutor = bindir / ("statutor.exe" if os.name == "nt" else "statutor")
    doctor = bindir / (
        "statutor-doctor.exe" if os.name == "nt" else "statutor-doctor")
    smoke_env = {**os.environ, "PYTHONPATH": str(site)}
    if not statutor.is_file() or not doctor.is_file():
        raise RuntimeError("wheel install did not create both console scripts")
    ledger = scratch / "ledger"
    ledger.mkdir()
    _run([str(statutor), "init", str(ledger)], env=smoke_env)
    _run(["git", "init", "-q", "-b", "main"], cwd=ledger)
    _run(["git", "config", "user.email", "release-gate@statutor.test"], cwd=ledger)
    _run(["git", "config", "user.name", "Statutor release gate"], cwd=ledger)
    _run(["git", "add", "-A"], cwd=ledger)
    _run(["git", "commit", "-q", "-m", "initialize ledger"], cwd=ledger)
    _run([str(statutor), "staged", str(ledger)], env=smoke_env)
    _run([str(doctor), str(ledger)], env=smoke_env)
    _run([
        str(statutor),
        "check",
        "write",
        json.dumps({
            "file_path": str(ledger / "plans" / "archive" / "denied.md"),
            "content": "denied",
        }),
        str(ledger),
    ], env=smoke_env, expected=2)

    global_home = scratch / "global-home"
    global_config = scratch / "global-config"
    global_state = scratch / "global-state"
    global_env = dict(smoke_env)
    for name in (
        "CLAUDE_CONFIG_DIR", "CODEX_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME",
    ):
        global_env.pop(name, None)
    roots = [
        "--home", str(global_home),
        "--config-root", str(global_config),
        "--state-root", str(global_state),
    ]
    _run([str(statutor), "global", "init", *roots, "--json"], env=global_env)
    _run([
        str(statutor), "global", "plan", *roots, "--host", "codex", "--json",
    ], env=global_env)
    _run([
        str(statutor), "global", "apply", *roots, "--host", "codex", "--json",
    ], env=global_env)
    if not (global_home / ".codex" / "AGENTS.md").is_file():
        raise RuntimeError("installed global CLI did not create Codex projection")
    if (global_home / ".claude" / "CLAUDE.md").exists():
        raise RuntimeError("host-scoped global apply touched unselected Claude target")

    skill_source = scratch / "fixture-skill"
    skill_source.mkdir()
    (skill_source / "SKILL.md").write_text(
        "---\nname: fixture-skill\ndescription: Release-gate fixture.\n"
        "custom-field: preserved\n---\n\n# Fixture\n",
        encoding="utf-8",
    )
    (skill_source / "reference.txt").write_text("v1\n", encoding="utf-8")
    _run([
        str(statutor), "global", "skill", "import", *roots,
        str(skill_source), "--json",
    ], env=global_env)
    _run([
        str(statutor), "global", "skill", "plan", *roots, "--json",
    ], env=global_env)
    _run([
        str(statutor), "global", "skill", "apply", *roots, "--json",
    ], env=global_env)
    _run([
        str(statutor), "global", "skill", "status", *roots, "--json",
    ], env=global_env)
    _run([
        str(statutor), "global", "status", *roots, "--json",
    ], env=global_env)
    _run([
        str(statutor), "global", "doctor", *roots, "--json",
    ], env=global_env)
    portable = global_home / ".agents" / "skills" / "fixture-skill"
    claude = global_home / ".claude" / "skills" / "fixture-skill"
    native_opencode = (
        global_home / ".config" / "opencode" / "skills" / "fixture-skill")
    if not portable.is_dir() or not claude.is_dir():
        raise RuntimeError("installed global CLI did not project fixture skill")
    if native_opencode.exists():
        raise RuntimeError("global skill apply created a third OpenCode copy")
    _run([
        str(statutor), "global", "skill", "uninstall", *roots, "--json",
    ], env=global_env)
    if portable.exists() or claude.exists():
        raise RuntimeError("global skill uninstall did not restore absent targets")


def _build_and_smoke(source: Path, workspace: Path, version: str) -> list[Path]:
    build_dir = workspace / "built"
    _run([
        sys.executable,
        "-m",
        "build",
        "--outdir",
        str(build_dir),
        str(source),
    ], cwd=workspace)
    sdist = build_dir / f"statutor-{version}.tar.gz"
    wheels = list(build_dir.glob(f"statutor-{version}-*.whl"))
    if not sdist.is_file() or len(wheels) != 1:
        raise RuntimeError("build did not produce exactly one wheel and one sdist")
    wheel = wheels[0]
    _audit_sdist(sdist, version)
    _audit_wheel(wheel, version)
    _smoke_wheel(wheel, workspace / "smoke")
    return [sdist, wheel]


def _verify_source(workspace: Path) -> None:
    env = {**os.environ, "STATUTOR_PACKAGE_AUDIT": "1"}
    _run([sys.executable, "core/statutor_doctor.py", "."])
    _run([sys.executable, "core/statutor_core.py", "staged", "."])
    _run([sys.executable, "-m", "pytest", "-q"], env=env)
    cargo_env = {
        **os.environ,
        "CARGO_TARGET_DIR": str(workspace / "cargo-target"),
    }
    _run([
        "cargo",
        "test",
        "--locked",
        "--release",
        "--manifest-path",
        "crates/statutor/Cargo.toml",
    ], env=cargo_env)
    tracked_target = subprocess.run(
        ["git", "ls-files", "--", "crates/statutor/target"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if tracked_target:
        raise RuntimeError("tracked Cargo target output:\n" + tracked_target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="require an exact v<python-version> tag")
    parser.add_argument(
        "--dist-dir",
        type=Path,
        help="copy verified artifacts here after every check passes",
    )
    parser.add_argument(
        "--versions-only",
        action="store_true",
        help="check and print metadata parity without building",
    )
    args = parser.parse_args(argv)

    found = versions()
    _check_tag(args.tag, found["python"])
    print("versions:", json.dumps(found, sort_keys=True), flush=True)
    if args.versions_only:
        return 0

    if shutil.which("cargo") is None or shutil.which("npm") is None:
        raise RuntimeError("release gate requires cargo and npm")
    try:
        __import__("build")
    except ImportError as error:
        raise RuntimeError(
            "release gate requires the 'build' package: python -m pip install build"
        ) from error

    output = args.dist_dir.resolve() if args.dist_dir else None
    if output is not None and output.exists() and any(output.iterdir()):
        raise RuntimeError(f"artifact output directory is not empty: {output}")

    with tempfile.TemporaryDirectory(prefix="statutor-release-") as temporary:
        workspace = Path(temporary)
        source = workspace / "source"
        source.mkdir()
        _candidate_tree(source)
        _verify_source(workspace)
        artifacts = _build_and_smoke(
            source, workspace, found["python"])
        if output is not None:
            output.mkdir(parents=True, exist_ok=True)
            for artifact in artifacts:
                shutil.copy2(artifact, output / artifact.name)

    print("OK: release gate passed", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
