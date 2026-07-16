"""Body-free fingerprints and recovery ownership boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import (
    _canonical_json,
    _is_int,
    _load_json,
    _regular_file,
    _require,
    _sha256,
    _sha256_path,
    _workspace_ref,
)
from .recovery_contracts import (
    OBSERVATION_FIELDS,
    RECEIPT_RECOVERY_STATUSES,
    ZERO_SHA256,
)

def _observation_sha256(value: dict[str, Any]) -> str:
    return _sha256(_canonical_json({field: value.get(field) for field in OBSERVATION_FIELDS}))

def _boundary_observation_sha256(value: dict[str, Any]) -> str:
    return _observation_sha256(value)

def _owned_write_paths(
    root: Path,
    plan: dict[str, Any],
    *,
    journal_state: str | None = None,
    publication_state: str | None = None,
) -> list[str]:
    values = {".task/index.lock"}
    if publication_state == "committed_render_pending":
        values.add(".task/index.md")
    elif journal_state in {"receipt_anchored", "committed_render_pending", "committed"}:
        values.update({
            ".task/index.md", plan["journal_ref"], plan["completion_marker_ref"],
        })
    elif journal_state == "receipt_written":
        values.update({
            ".task/index.jsonl", ".task/index.md", plan["journal_ref"],
            plan["receipt_ref"], plan["completion_marker_ref"],
        })
    else:
        values.update({
            ".task/index.jsonl", ".task/index.md", plan["journal_ref"],
            plan["receipt_ref"], plan["completion_marker_ref"],
            plan["render_snapshot_ref"],
        })
    for value in values:
        _workspace_ref(root, value, "recovery-owned path", must_exist=False)
    return sorted(values)

def _immutable_paths(plan: dict[str, Any]) -> list[str]:
    return sorted({
        plan["source_snapshot_ref"], plan["plan_snapshot_ref"],
        plan["mapping_manifest"]["snapshot_ref"], plan["resolution_manifest"]["ref"],
        plan["correction_suffix"]["ref"], plan["prepare_journal_ref"],
    })

def _owned_write_set_sha(paths: list[str]) -> str:
    return _sha256(_canonical_json(paths))

def _path_fingerprint(root: Path, relative: str) -> dict[str, Any]:
    path = _workspace_ref(root, relative, "recovery fingerprint path")
    return {
        "path_sha256": _sha256(relative.encode()),
        "size": path.stat().st_size,
        "sha256": _sha256_path(path),
    }

def _immutable_transaction_sha(root: Path, plan: dict[str, Any]) -> tuple[str, int]:
    paths = _immutable_paths(plan)
    return _sha256(_canonical_json([_path_fingerprint(root, path) for path in paths])), len(paths)

def _optional_sha(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, ZERO_SHA256
    _regular_file(path, "optional recovery surface")
    return True, _sha256_path(path)

def _optional_receipt(
    path: Path, transaction_id: str,
) -> tuple[bool, str, str, str]:
    if not path.exists():
        return False, ZERO_SHA256, "absent", ""
    receipt, payload = _load_json(path, "optional recovery receipt")
    _require(payload == _canonical_json(receipt), "recovery receipt is not canonical JSON")
    recovery_status = receipt.get("recovery_status")
    committed_at = receipt.get("transaction_committed_at")
    _require(
        _is_int(receipt.get("schema_version"))
        and receipt["schema_version"] == 2
        and receipt.get("kind") == "task_state_index_migration"
        and receipt.get("transaction_id") == transaction_id
        and receipt.get("status") == "committed"
        and recovery_status in RECEIPT_RECOVERY_STATUSES
        and isinstance(committed_at, str)
        and bool(committed_at)
        and receipt.get("transaction_started_at") == committed_at,
        "recovery receipt phase identity is invalid",
    )
    return True, _sha256(payload), recovery_status, committed_at

def _outside_owned_tree_sha(root: Path, owned: set[str]) -> str:
    inventory: list[dict[str, Any]] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        for item in sorted(directory.iterdir(), key=lambda value: value.name):
            relative = item.relative_to(root).as_posix()
            if item.is_symlink():
                inventory.append({"path_sha256": _sha256(relative.encode()), "kind": "symlink", "target_sha256": _sha256(str(item.readlink()).encode())})
            elif item.is_dir():
                inventory.append({"path_sha256": _sha256(relative.encode()), "kind": "directory"})
                pending.append(item)
            elif item.is_file() and relative not in owned:
                inventory.append({"path_sha256": _sha256(relative.encode()), "kind": "file", "size": item.stat().st_size, "sha256": _sha256_path(item)})
            elif not item.is_file():
                inventory.append({"path_sha256": _sha256(relative.encode()), "kind": "other"})
    inventory.sort(key=lambda entry: entry["path_sha256"])
    return _sha256(_canonical_json(inventory))

def _protected_anchor_sha(root: Path, plan: dict[str, Any]) -> str:
    values = []
    for label in ("current_task", "current_pack"):
        anchor = plan["anchors"][label]
        path = _workspace_ref(root, anchor["path"], f"protected {label} anchor")
        values.append({"label": label, "path_sha256": _sha256(anchor["path"].encode()), "content_sha256": _sha256_path(path)})
    return _sha256(_canonical_json(values))
