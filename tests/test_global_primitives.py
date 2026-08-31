"""Fake-root tests for the D-0018 global-layer safety substrate."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import statutor_global as global_layer


def test_resolve_posix_defaults_without_real_home(tmp_path: Path) -> None:
    roots = global_layer.resolve_roots(
        home=tmp_path / "home", environ={}, platform="posix")
    assert roots.to_json() == {
        "home": str(tmp_path / "home"),
        "config_root": str(tmp_path / "home/.config/statutor"),
        "state_root": str(tmp_path / "home/.local/state/statutor"),
        "claude_home": str(tmp_path / "home/.claude"),
        "codex_home": str(tmp_path / "home/.codex"),
        "opencode_home": str(tmp_path / "home/.config/opencode"),
        "portable_skills": str(tmp_path / "home/.agents/skills"),
    }


def test_resolve_host_environment_and_explicit_roots(tmp_path: Path) -> None:
    env = {
        "XDG_CONFIG_HOME": str(tmp_path / "xdg-config"),
        "XDG_STATE_HOME": str(tmp_path / "xdg-state"),
        "CLAUDE_CONFIG_DIR": str(tmp_path / "claude-profile"),
        "CODEX_HOME": str(tmp_path / "codex-profile"),
    }
    roots = global_layer.resolve_roots(
        home=tmp_path / "home",
        config_root=tmp_path / "explicit-config",
        state_root=tmp_path / "explicit-state",
        environ=env,
        platform="posix",
    )
    assert roots.config_root == str(tmp_path / "explicit-config")
    assert roots.state_root == str(tmp_path / "explicit-state")
    assert roots.claude_home == str(tmp_path / "claude-profile")
    assert roots.codex_home == str(tmp_path / "codex-profile")
    assert roots.opencode_home == str(tmp_path / "xdg-config/opencode")


def test_resolve_windows_defaults_are_explicit(tmp_path: Path) -> None:
    env = {
        "APPDATA": str(tmp_path / "Roaming"),
        "LOCALAPPDATA": str(tmp_path / "Local"),
    }
    roots = global_layer.resolve_roots(
        home=tmp_path / "User", environ=env, platform="nt")
    assert roots.config_root == str(tmp_path / "Roaming/statutor")
    assert roots.state_root == str(tmp_path / "Local/statutor/state")


def test_versioned_config_and_state_schemas() -> None:
    config = global_layer.default_config()
    state = global_layer.default_state()
    assert global_layer.validate_config(config) is config
    assert global_layer.validate_state(state) is state
    assert global_layer.canonical_json(config).endswith(b"\n")
    assert json.loads(global_layer.canonical_json(state))["generation"] == 0


def _receipt(tmp_path: Path) -> dict[str, object]:
    digest = "sha256:" + "a" * 64
    return {
        "kind": "instruction",
        "name": "global-instructions",
        "target_scope": "codex",
        "source_logical": str(tmp_path / "config/AGENTS.md"),
        "source_real": str(tmp_path / "config/AGENTS.md"),
        "target_logical": str(tmp_path / "home/.codex/AGENTS.md"),
        "target_real": str(tmp_path / "home/.codex/AGENTS.md"),
        "source_digest": digest,
        "installed_token": f"file:{digest}:0600",
        "backup_id": "op-1",
        "ownership": "statutor",
    }


def test_artifact_receipt_schema_is_strict(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    assert global_layer.validate_artifact_receipt(receipt) is receipt
    state = global_layer.default_state()
    state["artifacts"]["codex-instructions"] = receipt
    state["backups"]["op-1"] = "backups/op-1/manifest.json"
    assert global_layer.validate_state(state) is state


@pytest.mark.parametrize(
    "field,value,fragment",
    [
        ("ownership", "human", "ownership"),
        ("target_scope", "unknown", "target_scope"),
        ("source_digest", "sha256:short", "source_digest"),
        ("installed_token", "absent", "installed_token"),
        ("target_logical", "relative/path", "absolute"),
    ],
)
def test_artifact_receipt_rejects_unsafe_values(
    tmp_path: Path, field: str, value: object, fragment: str
) -> None:
    receipt = _receipt(tmp_path)
    receipt[field] = value
    with pytest.raises(global_layer.SchemaError, match=fragment):
        global_layer.validate_artifact_receipt(receipt)


@pytest.mark.parametrize(
    "mutate,fragment",
    [
        (lambda data: data.update(schema_version=99), "unsupported"),
        (
            lambda data: data["instructions"].update(common="../AGENTS.md"),
            "inside the config root",
        ),
        (lambda data: data.update(hosts=["codex", "codex"]), "unique"),
        (
            lambda data: data["skills"].update(targets=["opencode"]),
            "portable",
        ),
    ],
)
def test_config_schema_rejects_ambiguous_inputs(mutate, fragment: str) -> None:
    data = global_layer.default_config()
    mutate(data)
    with pytest.raises(global_layer.SchemaError, match=fragment):
        global_layer.validate_config(data)


def test_state_schema_rejects_unknown_fields() -> None:
    state = global_layer.default_state()
    state["surprise"] = True
    with pytest.raises(global_layer.SchemaError, match="unknown"):
        global_layer.validate_state(state)


def _make_tree(root: Path, reverse: bool = False) -> None:
    root.mkdir()
    entries = [("a.txt", b"a"), ("nested/b.txt", b"b")]
    if reverse:
        entries.reverse()
    for relative, content in entries:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        os.chmod(path, 0o644)


def test_tree_digest_is_order_independent_and_mode_sensitive(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _make_tree(first)
    _make_tree(second, reverse=True)
    baseline = global_layer.tree_digest(first)
    assert baseline == global_layer.tree_digest(second)
    os.chmod(second / "a.txt", 0o744)
    assert baseline != global_layer.tree_digest(second)


def test_tree_digest_accepts_internal_file_symlink(tmp_path: Path) -> None:
    root = tmp_path / "skill"
    root.mkdir()
    (root / "target.txt").write_text("target", encoding="utf-8")
    os.symlink("target.txt", root / "alias.txt")
    assert global_layer.tree_digest(root).startswith("sha256:")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
@pytest.mark.parametrize("case", ["broken", "escaping", "cycle"])
def test_tree_digest_rejects_unsafe_links(tmp_path: Path, case: str) -> None:
    root = tmp_path / "skill"
    root.mkdir()
    if case == "broken":
        os.symlink("missing", root / "link")
    elif case == "escaping":
        outside = tmp_path / "outside"
        outside.write_text("outside", encoding="utf-8")
        os.symlink("../outside", root / "link")
    else:
        nested = root / "nested"
        nested.mkdir()
        os.symlink("..", nested / "back")
    with pytest.raises(global_layer.UnsafeTree, match="broken|escapes|cyclic"):
        global_layer.tree_digest(root)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unavailable")
def test_tree_digest_rejects_special_files(tmp_path: Path) -> None:
    root = tmp_path / "skill"
    root.mkdir()
    os.mkfifo(root / "pipe")
    with pytest.raises(global_layer.UnsafeTree, match="special file"):
        global_layer.tree_digest(root)


def test_atomic_file_compare_and_swap(tmp_path: Path) -> None:
    target = tmp_path / "state/config.json"
    first = global_layer.atomic_write_bytes(
        target, b"one", expected=global_layer.ABSENT, mode=0o600)
    assert target.read_bytes() == b"one"
    assert first.token == global_layer.fingerprint(target).token
    second = global_layer.atomic_write_bytes(
        target, b"two", expected=first.token, mode=0o640)
    assert target.read_bytes() == b"two"
    assert second.mode == 0o640
    with pytest.raises(global_layer.ConcurrentChange):
        global_layer.atomic_write_bytes(target, b"lost", expected=first.token)
    assert target.read_bytes() == b"two"


def test_atomic_file_refuses_target_entry_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.write_text("keep", encoding="utf-8")
    link = tmp_path / "link"
    os.symlink(real.name, link)
    before = global_layer.fingerprint(link)
    with pytest.raises(global_layer.GlobalError, match="non-file"):
        global_layer.atomic_write_bytes(link, b"replace", expected=before.token)
    assert real.read_text(encoding="utf-8") == "keep"


def test_atomic_tree_compare_and_swap(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _make_tree(source)
    target = tmp_path / "installed"
    installed = global_layer.atomic_replace_tree(
        target, source, expected=global_layer.ABSENT)
    assert installed.kind == "tree"
    assert (target / "nested/b.txt").read_bytes() == b"b"
    changed = tmp_path / "changed"
    _make_tree(changed)
    (changed / "a.txt").write_text("changed", encoding="utf-8")
    updated = global_layer.atomic_replace_tree(
        target, changed, expected=installed.token)
    assert updated.token != installed.token
    with pytest.raises(global_layer.ConcurrentChange):
        global_layer.atomic_replace_tree(target, source, expected=installed.token)


def test_state_lock_serializes_operations(tmp_path: Path) -> None:
    with global_layer.StateLock(tmp_path / "state"):
        with pytest.raises(global_layer.LockBusy):
            with global_layer.StateLock(tmp_path / "state"):
                pass
    with global_layer.StateLock(tmp_path / "state"):
        assert (tmp_path / "state/.global.lock/owner.json").is_file()


def test_journal_is_cas_updated(tmp_path: Path) -> None:
    path, journal = global_layer.create_journal(
        tmp_path / "state",
        action="global-apply",
        plan_digest="sha256:plan",
        operation_id="op-1",
    )
    updated, result = global_layer.update_journal(
        path,
        journal,
        status="applying",
        step={"artifact": "codex-instructions", "status": "installed"},
    )
    assert result.token == global_layer.fingerprint(path).token
    assert updated["steps"] == [
        {"artifact": "codex-instructions", "status": "installed"}
    ]
    assert global_layer.load_json(path)["status"] == "applying"


def test_file_backup_and_restore_are_exact(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("before", encoding="utf-8")
    os.chmod(target, 0o640)
    manifest, _ = global_layer.create_backup(
        tmp_path / "state",
        target,
        operation_id="op-file",
        artifact_id="instructions",
    )
    before = global_layer.fingerprint(target)
    current = global_layer.atomic_write_bytes(
        target, b"after", expected=before.token)
    restored = global_layer.restore_backup(
        manifest, target, expected_current=current.token)
    assert restored.mode == 0o640
    assert target.read_text(encoding="utf-8") == "before"


def test_absent_backup_restore_removes_only_expected_current(tmp_path: Path) -> None:
    target = tmp_path / "new.txt"
    manifest, _ = global_layer.create_backup(
        tmp_path / "state",
        target,
        operation_id="op-absent",
        artifact_id="new-file",
    )
    current = global_layer.atomic_write_bytes(
        target, b"created", expected=global_layer.ABSENT)
    restored = global_layer.restore_backup(
        manifest, target, expected_current=current.token)
    assert restored.kind == global_layer.ABSENT
    assert not target.exists()


def test_tree_backup_restore_recovers_content(tmp_path: Path) -> None:
    target = tmp_path / "skill"
    _make_tree(target)
    manifest, _ = global_layer.create_backup(
        tmp_path / "state",
        target,
        operation_id="op-tree",
        artifact_id="skill",
    )
    original = global_layer.fingerprint(target)
    replacement = tmp_path / "replacement"
    _make_tree(replacement)
    (replacement / "a.txt").write_text("replacement", encoding="utf-8")
    current = global_layer.atomic_replace_tree(
        target, replacement, expected=original.token)
    restored = global_layer.restore_backup(
        manifest, target, expected_current=current.token)
    assert restored.token == original.token
    assert (target / "a.txt").read_text(encoding="utf-8") == "a"


def test_symlink_backup_restore_does_not_follow_target(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("real", encoding="utf-8")
    target = tmp_path / "projection"
    os.symlink(real.name, target)
    manifest, _ = global_layer.create_backup(
        tmp_path / "state",
        target,
        operation_id="op-link",
        artifact_id="link",
    )
    original = global_layer.fingerprint(target)
    target.unlink()
    current = global_layer.atomic_write_bytes(
        target, b"managed", expected=global_layer.ABSENT)
    restored = global_layer.restore_backup(
        manifest, target, expected_current=current.token)
    assert restored.token == original.token
    assert target.is_symlink()
    assert real.read_text(encoding="utf-8") == "real"
