"""statutor middleware for a custom harness (e.g. Hermes executors).

You own the harness, so the adapter is a function call: run validate()
before dispatching any file-writing or shell tool.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
from statutor_core import validate  # noqa: E402


class StatutorDenied(PermissionError):
    pass


def guard_tool_call(tool: str, args: dict, workdir: str) -> None:
    """Call before executing a tool. Raises StatutorDenied on policy violation.

    tool: "write" | "edit" | "bash" (others pass through)
    args: {"file_path"/"filePath", "content"} or {"old_string", "new_string"}
          or {"command"} for bash
    """
    reason = validate(tool, args, workdir)
    if reason:
        raise StatutorDenied(f"[statutor] {reason}")


if __name__ == "__main__":  # smoke test
    try:
        guard_tool_call("bash", {"command": "echo x >> DECISIONS.md"}, ".")
    except StatutorDenied as e:
        print("denied as expected:", e)
