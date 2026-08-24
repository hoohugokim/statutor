"""statutor ledger-policy plugin for Hermes Agent (T-0010).

In-loop enforcement: the pre_tool_call hook maps Hermes tools onto the
kernel's validate() core and returns a blocking directive on violation
(Hermes translates {"action": "block", "message": ...} into the tool
result the model sees; see hermes_cli/plugins.py _get_pre_tool_call_
directive_details in any checkout):

  write_file {path, content}            -> validate("write", ...)
  patch {mode="replace", path, ...}     -> validate("edit", ...)
  patch {mode="patch", patch}           -> validate("apply_patch", ...)  V4A
  terminal  {command}                   -> validate("bash", ...)

Kernel resolution (first hit wins):
  1. import statutor_core — pip-installed into Hermes's own interpreter
     (`pip install statutor` into the env Hermes runs with; a pipx venv
     is NOT importable from here)
  2. $STATUTOR_KERNEL — explicit path to core/statutor_core.py
  3. sibling statutor_core.py — a copy dropped next to this file;
     convenient, but it forks the kernel and will drift

Fail-open everywhere: an unavailable or broken kernel must never break a
session — coverage degrades to the git floor (adapters/git/), which stays
mandatory. Stdlib only.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, Optional

_kernel = None
_resolved = False


def _load_kernel():
    try:
        import statutor_core  # noqa: F401 — resolution path 1

        return sys.modules["statutor_core"]
    except Exception:
        pass
    candidate = os.environ.get("STATUTOR_KERNEL") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "statutor_core.py")
    if os.path.isfile(candidate):
        try:
            spec = importlib.util.spec_from_file_location("statutor_core_hermes", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception:
            return None
    return None


def _kernel_module():
    global _kernel, _resolved
    if not _resolved:
        _resolved = True
        _kernel = _load_kernel()
    return _kernel


def _check(tool: str, payload: dict) -> Optional[str]:
    module = _kernel_module()
    if module is None:
        return None
    try:
        return module.validate(tool, payload, os.getcwd())
    except Exception:
        return None  # fail open


def pre_tool_call(**kwargs: Any):
    """pre_tool_call hook: block directive on a ledger-policy violation."""
    tool_name = str(kwargs.get("tool_name") or "").lower()
    args = kwargs.get("args")
    if not isinstance(args, dict):
        return None

    if tool_name == "write_file":
        reason = _check("write", {"file_path": args.get("path", ""),
                                  "content": args.get("content", "")})
    elif tool_name == "patch":
        if str(args.get("mode") or "replace") == "patch":
            reason = _check("apply_patch", {"command": args.get("patch", "")})
        else:
            reason = _check("edit", {"file_path": args.get("path", ""),
                                     "old_string": args.get("old_string", ""),
                                     "new_string": args.get("new_string", "")})
    elif tool_name == "terminal":
        reason = _check("bash", {"command": args.get("command", "")})
    else:
        return None

    if reason:
        return {"action": "block", "message": f"[statutor] {reason}"}
    return None


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", pre_tool_call)
