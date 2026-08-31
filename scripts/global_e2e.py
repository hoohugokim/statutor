#!/usr/bin/env python3
"""Opt-in current-release E2E for the v0.4 global layer under fake homes.

This script never points a host at the caller's real home and never performs a
model or network request. It exercises native read-only diagnostics where a
host exposes them, then proves Statutor's modified-target refusal and exact
uninstall recovery. It is intentionally separate from the hermetic release
gate because it requires locally installed host binaries.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import statutor_global as substrate  # noqa: E402
import statutor_global_cli as instructions  # noqa: E402
import statutor_global_status as diagnostics  # noqa: E402
import statutor_skills as skills  # noqa: E402


EXPECTED_VERSIONS = {
    "claude": "2.1.251",
    "codex": "0.151.0",
    "opencode": "1.18.20",
}
GLOBAL_MARKER = "STATUTOR_E2E_GLOBAL_INSTRUCTION_7F6A1D"
SKILL_NAME = "statutor-e2e-skill"


class E2EError(RuntimeError):
    pass


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True,
        timeout=timeout, check=False)
    if result.returncode != 0:
        raise E2EError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout: {result.stdout[-2000:]}\n"
            f"stderr: {result.stderr[-2000:]}")
    return result


def _version(host: str, binary: str, env: dict[str, str], cwd: Path) -> str:
    output = _run([binary, "--version"], cwd=cwd, env=env).stdout
    match = re.search(r"(?<![0-9])([0-9]+\.[0-9]+\.[0-9]+)(?![0-9])", output)
    if match is None:
        raise E2EError(f"cannot parse {host} version from {output!r}")
    version = match.group(1)
    if version != EXPECTED_VERSIONS[host]:
        raise E2EError(
            f"{host} version {version} != tested baseline "
            f"{EXPECTED_VERSIONS[host]}")
    return version


def _fake_env(profile: Path, roots: substrate.ResolvedRoots) -> dict[str, str]:
    env = dict(os.environ)
    for name in (
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
        "OPENCODE_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY",
    ):
        env.pop(name, None)
    replacements = {
        "HOME": roots.home,
        "CLAUDE_CONFIG_DIR": roots.claude_home,
        "CODEX_HOME": roots.codex_home,
        "XDG_CONFIG_HOME": str(profile / "xdg-config"),
        "XDG_DATA_HOME": str(profile / "xdg-data"),
        "XDG_STATE_HOME": str(profile / "xdg-state"),
        "XDG_CACHE_HOME": str(profile / "xdg-cache"),
        "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
        "NO_COLOR": "1",
        "TERM": "dumb",
        "CI": "1",
    }
    env.update(replacements)
    for name in ("xdg-config", "xdg-data", "xdg-state", "xdg-cache"):
        (profile / name).mkdir(parents=True, exist_ok=True)
    return env


def _write_sources(roots: substrate.ResolvedRoots, profile: Path) -> Path:
    common = Path(roots.config_root) / "AGENTS.md"
    substrate.atomic_write_bytes(
        common, f"# {GLOBAL_MARKER}\n".encode(),
        expected=substrate.fingerprint(common).token)
    for host in substrate.HOSTS:
        overlay = Path(roots.config_root) / f"hosts/{host}.md"
        substrate.atomic_write_bytes(
            overlay, f"# STATUTOR_E2E_{host.upper()}_OVERLAY\n".encode(),
            expected=substrate.fingerprint(overlay).token)
    source = profile / "fixture-source" / SKILL_NAME
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        f"---\nname: {SKILL_NAME}\n"
        "description: Exercise the Statutor fake-profile release probe.\n"
        "e2e-extension: preserved\n---\n\n# E2E fixture\n",
        encoding="utf-8")
    (source / "payload.txt").write_text("release-probe\n", encoding="utf-8")
    return source


def _projection_evidence(
    roots: substrate.ResolvedRoots,
) -> dict[str, object]:
    instruction_items = []
    for host in substrate.HOSTS:
        target = instructions.instruction_target(roots, host)
        content = target.read_text(encoding="utf-8")
        instruction_items.append({
            "host": host,
            "path": str(target),
            "global_marker_count": content.count(GLOBAL_MARKER),
            "host_overlay_count": content.count(
                f"STATUTOR_E2E_{host.upper()}_OVERLAY"),
        })
    skill_items = []
    for scope, target in skills._skill_targets(roots, SKILL_NAME):
        skill_items.append({
            "scope": scope,
            "path": str(target),
            "digest": substrate.tree_digest(target),
        })
    if any(
        item["global_marker_count"] != 1 or item["host_overlay_count"] != 1
        for item in instruction_items
    ):
        raise E2EError("an instruction projection did not contain each marker once")
    if len({item["digest"] for item in skill_items}) != 1:
        raise E2EError("host skill projections are not identical")
    return {"instructions": instruction_items, "skills": skill_items}


def _codex_probe(binary: str, project: Path, env: dict[str, str]) -> dict[str, object]:
    result = _run(
        [binary, "debug", "prompt-input", "STATUTOR_E2E_USER_PROMPT"],
        cwd=project, env=env)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise E2EError("Codex prompt-input did not emit JSON") from error
    rendered = json.dumps(payload, ensure_ascii=False)
    instruction_count = rendered.count(GLOBAL_MARKER)
    skill_contexts: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, str) and SKILL_NAME in value:
            skill_contexts.append(value)
        elif isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)

    collect(payload)
    if instruction_count != 1 or len(skill_contexts) != 1:
        raise E2EError(
            "Codex model-visible prompt did not report the fixture instruction "
            "and one fixture skill catalog entry")
    return {
        "surface": "debug prompt-input",
        "instruction_marker_count": instruction_count,
        "skill_catalog_entries": len(skill_contexts),
        "skill_name_mentions_in_entry": skill_contexts[0].count(SKILL_NAME),
    }


def _opencode_probe(
    binary: str, project: Path, env: dict[str, str],
) -> dict[str, object]:
    result = _run(
        [binary, "debug", "skill", "--pure"], cwd=project, env=env)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise E2EError("OpenCode debug skill did not emit JSON") from error
    matches = [item for item in payload if item.get("name") == SKILL_NAME]
    if len(matches) != 1:
        raise E2EError(
            f"OpenCode reported {len(matches)} entries for the duplicated fixture")
    return {
        "surface": "debug skill --pure",
        "skill_entries": len(matches),
        "location": matches[0].get("location"),
        "instruction_contract": "native AGENTS projection verified on disk",
    }


def _claude_probe(
    binary: str, project: Path, env: dict[str, str],
) -> dict[str, object]:
    listing = _run(
        [binary, "plugin", "list", "--json"], cwd=project, env=env)
    try:
        payload = json.loads(listing.stdout)
    except json.JSONDecodeError as error:
        raise E2EError("Claude plugin list did not emit JSON") from error
    rendered = json.dumps(payload, ensure_ascii=False)
    mentions = rendered.count(SKILL_NAME)
    return {
        "surface": "plugin list --json",
        "skill_name_mentions": mentions,
        "offline_discovery_surface": False,
        "note": (
            "Claude 2.1.251 exposes no offline model-context/skill inventory; "
            "plugin list does not enumerate personal skills"),
        "instruction_contract": "native CLAUDE.md projection verified on disk",
    }


def _refusal_and_uninstall(
    roots: substrate.ResolvedRoots,
) -> dict[str, object]:
    codex = instructions.instruction_target(roots, "codex")
    installed_instruction = codex.read_bytes()
    changed = substrate.atomic_write_bytes(
        codex, b"human edit\n", expected=substrate.fingerprint(codex).token)
    instruction_refused = False
    try:
        instructions.apply_instructions(roots)
    except substrate.GlobalError:
        instruction_refused = True
    if not instruction_refused:
        raise E2EError("instruction sync did not refuse a modified target")
    substrate.atomic_write_bytes(
        codex, installed_instruction, expected=changed.token, mode=0o600)

    portable = Path(roots.portable_skills) / SKILL_NAME
    installed_skill = Path(roots.config_root) / "skills" / SKILL_NAME
    (portable / "payload.txt").write_text("human edit\n", encoding="utf-8")
    skill_refused = False
    try:
        skills.apply_skills(roots)
    except substrate.GlobalError:
        skill_refused = True
    if not skill_refused:
        raise E2EError("skill sync did not refuse a modified target")
    substrate.atomic_replace_tree(
        portable, installed_skill, expected=substrate.fingerprint(portable).token)

    skills.uninstall_skills(roots)
    instructions.uninstall_instructions(roots)
    remaining = [
        str(path) for path in (
            *(instructions.instruction_target(roots, host)
              for host in substrate.HOSTS),
            *(target for _, target in skills._skill_targets(roots, SKILL_NAME)),
        ) if path.exists() or path.is_symlink()
    ]
    if remaining:
        raise E2EError(f"uninstall did not restore initially absent targets: {remaining}")
    return {
        "instruction_modified_refused": instruction_refused,
        "skill_modified_refused": skill_refused,
        "uninstall_restored_absence": True,
    }


def run(hosts: list[str]) -> dict[str, object]:
    binaries = {}
    for host in hosts:
        binary = shutil.which(host)
        if binary is None:
            raise E2EError(f"required host binary is missing: {host}")
        binaries[host] = binary
    with tempfile.TemporaryDirectory(prefix="statutor-global-e2e-") as temporary:
        profile = Path(temporary)
        roots = substrate.resolve_roots(
            home=profile / "home",
            config_root=profile / "config/statutor",
            state_root=profile / "state/statutor",
            environ={
                "HOME": str(profile / "home"),
                "CLAUDE_CONFIG_DIR": str(profile / "home/.claude"),
                "CODEX_HOME": str(profile / "home/.codex"),
                "XDG_CONFIG_HOME": str(profile / "xdg-config"),
            },
            platform="posix",
        )
        env = _fake_env(profile, roots)
        project = profile / "project"
        project.mkdir()
        instructions.global_init(roots)
        source = _write_sources(roots, profile)
        skills.import_skill(roots, source)
        instructions.apply_instructions(roots)
        skills.apply_skills(roots)
        audit = diagnostics.global_doctor(
            roots, admin_root=profile / "admin-skills")
        if audit["summary"]["errors"]:
            raise E2EError(f"Statutor doctor rejected fixture: {audit['diagnostics']}")
        projection = _projection_evidence(roots)
        versions = {
            host: _version(host, binaries[host], env, project) for host in hosts
        }
        probes = {}
        if "codex" in hosts:
            probes["codex"] = _codex_probe(binaries["codex"], project, env)
        if "opencode" in hosts:
            probes["opencode"] = _opencode_probe(
                binaries["opencode"], project, env)
        if "claude" in hosts:
            probes["claude"] = _claude_probe(
                binaries["claude"], project, env)
        safety = _refusal_and_uninstall(roots)
        return {
            "schema_version": 1,
            "hosts": hosts,
            "versions": versions,
            "projections": projection,
            "native_probes": probes,
            "safety": safety,
            "real_home_mutated": False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host", action="append", choices=substrate.HOSTS,
        help="host to probe; repeat (default: all)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    hosts = [host for host in substrate.HOSTS if not args.host or host in args.host]
    try:
        result = run(hosts)
    except (E2EError, substrate.GlobalError, OSError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        for host in hosts:
            print(f"OK {host} {result['versions'][host]}")
        print("OK modified-target refusal and uninstall recovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
