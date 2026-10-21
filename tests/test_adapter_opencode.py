"""Contract and behavior checks for the OpenCode adapter (v1 `server` + v2 `setup`).

The behavioral cases use a source CLI shim and need Node with TypeScript
type stripping (22.6+). The release gate requires that runtime.

The v2 cases use the real 2.0.32 vocabulary (`shell`, `write`, `edit`, `patch`)
and argument shapes (`path`, `patchText`), which differ from v1 (`bash`,
`filePath`, `command`). The adapter normalizes both to the kernel's canonical
names; these tests fail if a future rename slips through again.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "opencode" / "statutor.ts"

HARNESS = """
import { pathToFileURL } from "node:url"

const [adapter, ledger, api] = process.argv.slice(2)
const mod = await import(pathToFileURL(adapter).href)

const patch = "*** Begin Patch\\n*** Delete File: plans/archive/probe.md\\n*** End Patch"
const cases =
  api === "v1"
    ? {
        write: ["write", { filePath: "plans/archive/probe.md", content: "x" }],
        edit: ["edit", { filePath: "plans/archive/probe.md", oldString: "a", newString: "b" }],
        patch: ["apply_patch", { command: patch }],
        shell: ["bash", { command: "echo probe > /tmp/TASKS.md" }],
        plain: ["write", { filePath: "notes/probe.md", content: "x" }],
        unguarded: ["read", { filePath: "plans/archive/probe.md" }],
      }
    : {
        write: ["write", { path: "plans/archive/probe.md", content: "x" }],
        edit: ["edit", { path: "plans/archive/probe.md", oldString: "a", newString: "b" }],
        patch: ["patch", { patchText: patch }],
        shell: ["shell", { command: "echo probe > /tmp/TASKS.md" }],
        plain: ["write", { path: "notes/probe.md", content: "x" }],
        unguarded: ["read", { path: "plans/archive/probe.md" }],
      }

let hook
if (api === "v1") {
  const hooks = await mod.default.server({ directory: ledger })
  hook = hooks["tool.execute.before"]
} else {
  const handlers = new Map()
  await mod.default.setup({
    location: { directory: ledger },
    tool: { hook: async (name, handler) => handlers.set(name, handler) },
  })
  hook = handlers.get("execute.before")
}
if (typeof hook !== "function") throw new Error(`no hook registered for ${api}`)

const results = { id: mod.default.id }
for (const [label, [tool, input]] of Object.entries(cases)) {
  try {
    if (api === "v1") await hook({ tool }, { args: input })
    else await hook({ tool, input })
    results[label] = "allowed"
  } catch (error) {
    results[label] = `blocked:${error.message}`
  }
}
process.stdout.write(JSON.stringify(results))
"""


def _node() -> str:
    executable = shutil.which("node")
    if executable is None:
        if os.environ.get("STATUTOR_PACKAGE_AUDIT") == "1":
            pytest.fail("release gate requires node for adapter behavior checks")
        pytest.skip("node is unavailable")
    raw = subprocess.run([executable, "--version"], capture_output=True, text=True, check=True).stdout
    match = re.match(r"v(\d+)\.(\d+)", raw)
    assert match is not None, raw
    major, minor = int(match.group(1)), int(match.group(2))
    if (major, minor) < (22, 6):
        if os.environ.get("STATUTOR_PACKAGE_AUDIT") == "1":
            pytest.fail(f"release gate requires Node 22.6+, got {raw.strip()}")
        pytest.skip(f"node {raw.strip()} cannot strip TypeScript types")
    return executable


def _ledger(tmp_path: Path) -> Path:
    (tmp_path / ".statutor.yaml").write_text(
        "governed:\n  - pattern: plans/archive/*\n    policy: frozen\n",
        encoding="utf-8",
    )
    return tmp_path


def _run(tmp_path: Path, api: str, env: dict[str, str] | None = None) -> dict[str, str]:
    node = _node()
    if env is None:
        bindir = tmp_path / "candidate-bin"
        bindir.mkdir()
        shim = bindir / "statutor"
        shim.write_text(
            f"#!{sys.executable}\nimport sys\n"
            f"sys.path.insert(0, {str(ROOT / 'core')!r})\n"
            "from statutor_core import main\nmain()\n", encoding="utf-8")
        shim.chmod(0o755)
        env = {**os.environ, "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", "")}
    harness = tmp_path / "adapter_probe.mjs"
    harness.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        [node, str(harness), str(ADAPTER), str(_ledger(tmp_path)), api],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_adapter_declares_both_plugin_entrypoints() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    assert "export default" in source
    assert re.search(r'^\s*id: "statutor",$', source, re.MULTILINE)
    assert "async setup(ctx: V2Context)" in source
    assert "async server(ctx: V1Context)" in source
    assert 'ctx.tool.hook("execute.before"' in source
    assert '"tool.execute.before"' in source


def test_adapter_maps_both_harness_vocabularies() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    for key, value in {
        "bash": "bash",
        "shell": "bash",
        "write": "write",
        "edit": "edit",
        "patch": "apply_patch",
        "apply_patch": "apply_patch",
    }.items():
        assert re.search(rf'^\s*{key}: "{value}",$', source, re.MULTILINE), key
    assert "payload.path ?? payload.filePath" in source
    assert "payload.patchText ?? payload.patch" in source
    assert '["check", "--if-ledger", tool, encode(input), directory]' in source


def test_adapter_fails_open_on_spawn_errors() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    assert 'child.on("error"' in source
    assert 'settle({ code: 0, stderr: "" })' in source
    assert 'return "{}"' in source


@pytest.mark.parametrize("api", ["v2", "v1"])
def test_guard_blocks_every_canonical_shape(tmp_path: Path, api: str) -> None:
    result = _run(tmp_path, api)
    assert result["id"] == "statutor"
    for label in ("write", "edit", "patch", "shell"):
        assert result[label].startswith("blocked:"), (label, result[label])
    assert result["plain"] == "allowed"
    assert result["unguarded"] == "allowed"


def test_adapter_probe_uses_candidate_instead_of_installed_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign = tmp_path / "foreign-bin"
    foreign.mkdir()
    executable = foreign / "statutor"
    executable.write_text(f"#!{sys.executable}\nraise SystemExit(0)\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(foreign) + os.pathsep + os.environ.get("PATH", ""))
    result = _run(tmp_path, "v2")
    assert result["write"].startswith("blocked:")


@pytest.mark.parametrize("api", ["v2", "v1"])
def test_missing_cli_fails_open(tmp_path: Path, api: str) -> None:
    empty = tmp_path / "empty-path"
    empty.mkdir()
    env = {"PATH": str(empty)}
    result = _run(tmp_path, api, env=env)
    for label in ("write", "edit", "patch", "shell", "plain"):
        assert result[label] == "allowed", (label, result[label])
