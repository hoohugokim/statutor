"""Deterministic Cargo/npm payload audits for the native adapters (T-0023).

The metadata checks always run. Real pack commands run once in the dedicated
CI leg when STATUTOR_PACKAGE_AUDIT=1, rather than opportunistically using
whatever Cargo and Node versions happen to be on every Python matrix runner.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_LICENSE = REPO_ROOT / "LICENSE"
CRATE = REPO_ROOT / "crates" / "statutor"
NPM_PACKAGE = REPO_ROOT / "adapters" / "opencode"
PACKAGE_AUDIT = os.environ.get("STATUTOR_PACKAGE_AUDIT") == "1"

CARGO_INCLUDE = [
    "/src/lib.rs",
    "/src/main.rs",
    "/README.md",
    "/LICENSE",
]
NPM_FILES = ["statutor.ts", "README.md", "LICENSE"]


def _cargo_package_table() -> str:
    manifest = (CRATE / "Cargo.toml").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^\[package\]\n(.*?)(?=^\[|\Z)", manifest)
    assert match is not None, "Cargo.toml has no [package] table"
    return match.group(1)


def _cargo_value(table: str, key: str) -> str:
    match = re.search(rf'(?m)^{re.escape(key)}\s*=\s*"([^"]+)"$', table)
    assert match is not None, f"Cargo.toml [package] has no string {key}"
    return match.group(1)


def _cargo_array(table: str, key: str) -> list[str]:
    match = re.search(rf"(?ms)^{re.escape(key)}\s*=\s*\[(.*?)^\]", table)
    assert match is not None, f"Cargo.toml [package] has no array {key}"
    return re.findall(r'"([^"]+)"', match.group(1))


def _tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        pytest.fail(f"STATUTOR_PACKAGE_AUDIT=1 but {name} is unavailable")
    return executable


def _archive_payload(path: Path, expected_root: str) -> dict[str, bytes]:
    with tarfile.open(path, mode="r:*") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        assert len(names) == len(set(names)), "archive contains duplicate paths"
        assert all(member.isfile() for member in members), (
            "archive contains a directory, link, or special file")
        assert all(member.mode & 0o111 == 0 for member in members), (
            "archive contains an executable payload member")

        payload: dict[str, bytes] = {}
        for member in members:
            archive_path = PurePosixPath(member.name)
            assert not archive_path.is_absolute()
            assert archive_path.parts[0] == expected_root
            assert ".." not in archive_path.parts
            assert "target" not in archive_path.parts
            extracted = archive.extractfile(member)
            assert extracted is not None
            payload[member.name] = extracted.read()

    checkout = str(REPO_ROOT).encode()
    private_path_markers = (checkout, b"/Users/", b"/home/", b"C:\\Users\\")
    for name, content in payload.items():
        content.decode("utf-8")  # Reject Mach-O, ELF, rlibs, and other binaries.
        for marker in private_path_markers:
            assert marker not in content, f"private build path in {name}"
    return payload


def test_package_metadata_is_explicit_and_versioned() -> None:
    cargo_table = _cargo_package_table()
    cargo_version = _cargo_value(cargo_table, "version")
    assert cargo_version == "0.1.1"
    assert _cargo_array(cargo_table, "include") == CARGO_INCLUDE

    cargo_lock = (CRATE / "Cargo.lock").read_text(encoding="utf-8")
    locked = re.search(
        r'(?ms)^\[\[package\]\]\nname = "statutor"\nversion = "([^"]+)"',
        cargo_lock,
    )
    assert locked is not None and locked.group(1) == cargo_version

    npm_manifest = json.loads((NPM_PACKAGE / "package.json").read_text())
    assert npm_manifest["version"] == "0.1.1"
    assert npm_manifest["files"] == NPM_FILES
    lifecycle_scripts = {
        "prepublish",
        "prepublishOnly",
        "prepack",
        "prepare",
        "postpack",
        "publish",
        "postpublish",
    }
    assert lifecycle_scripts.isdisjoint(npm_manifest.get("scripts", {})), (
        "package lifecycle scripts would make --ignore-scripts audit a different pack")
    assert f'statutor@{npm_manifest["version"]}' in (
        NPM_PACKAGE / "README.md").read_text(encoding="utf-8")

    license_bytes = ROOT_LICENSE.read_bytes()
    assert (CRATE / "LICENSE").read_bytes() == license_bytes
    assert (NPM_PACKAGE / "LICENSE").read_bytes() == license_bytes


@pytest.mark.skipif(
    not PACKAGE_AUDIT,
    reason="real package audit runs in the dedicated CI leg",
)
def test_cargo_package_payload(tmp_path: Path) -> None:
    cargo = _tool("cargo")
    cargo_version = _cargo_value(_cargo_package_table(), "version")
    target_dir = tmp_path / "cargo-target"
    env = {**os.environ, "CARGO_TARGET_DIR": str(target_dir)}
    package = subprocess.run(
        [
            cargo,
            "package",
            "--no-verify",
            "--allow-dirty",
            "--locked",
            "--offline",
            "--manifest-path",
            str(CRATE / "Cargo.toml"),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert package.returncode == 0, package.stderr

    crate_path = target_dir / "package" / f"statutor-{cargo_version}.crate"
    assert crate_path.is_file(), package.stdout
    assert crate_path.stat().st_size < 256_000

    prefix = f"statutor-{cargo_version}"
    expected = {
        f"{prefix}/.cargo_vcs_info.json",
        f"{prefix}/Cargo.lock",
        f"{prefix}/Cargo.toml",
        f"{prefix}/Cargo.toml.orig",
        f"{prefix}/LICENSE",
        f"{prefix}/README.md",
        f"{prefix}/src/lib.rs",
        f"{prefix}/src/main.rs",
    }
    payload = _archive_payload(crate_path, prefix)
    assert set(payload) == expected

    source_files = {
        "Cargo.lock": CRATE / "Cargo.lock",
        "Cargo.toml.orig": CRATE / "Cargo.toml",
        "LICENSE": CRATE / "LICENSE",
        "README.md": CRATE / "README.md",
        "src/lib.rs": CRATE / "src" / "lib.rs",
        "src/main.rs": CRATE / "src" / "main.rs",
    }
    for relative, source in source_files.items():
        assert payload[f"{prefix}/{relative}"] == source.read_bytes()


@pytest.mark.skipif(
    not PACKAGE_AUDIT,
    reason="real package audit runs in the dedicated CI leg",
)
def test_npm_package_payload(tmp_path: Path) -> None:
    npm = _tool("npm")
    env = {**os.environ, "NPM_CONFIG_CACHE": str(tmp_path / "npm-cache")}
    package = subprocess.run(
        [
            npm,
            "pack",
            "--json",
            "--ignore-scripts",
            "--pack-destination",
            str(tmp_path),
        ],
        cwd=NPM_PACKAGE,
        env=env,
        capture_output=True,
        text=True,
    )
    assert package.returncode == 0, package.stderr
    reports = json.loads(package.stdout)
    assert len(reports) == 1
    report = reports[0]

    manifest = json.loads((NPM_PACKAGE / "package.json").read_text())
    assert report["name"] == manifest["name"]
    assert report["version"] == manifest["version"]
    assert sorted(entry["path"] for entry in report["files"]) == sorted(
        ["LICENSE", "README.md", "package.json", "statutor.ts"]
    )

    tarball = tmp_path / report["filename"]
    assert tarball.is_file()
    assert tarball.stat().st_size < 256_000
    payload = _archive_payload(tarball, "package")
    expected = {
        "package/LICENSE",
        "package/README.md",
        "package/package.json",
        "package/statutor.ts",
    }
    assert set(payload) == expected

    for relative in ("LICENSE", "README.md", "package.json", "statutor.ts"):
        assert payload[f"package/{relative}"] == (NPM_PACKAGE / relative).read_bytes()
