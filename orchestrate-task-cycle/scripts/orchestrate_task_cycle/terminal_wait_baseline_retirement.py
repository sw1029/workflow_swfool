"""Immutable retirement lifecycle for active terminal-wait baselines."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .terminal_wait_baseline_store import (
    display_bytes,
    mutation_lock,
    read_bound_json,
    read_current_bytes,
    sha256_bytes,
    write_current,
    write_once,
)
from .terminal_wait_baseline_validation import POINTER_KEYS, load_current_pointer


INACTIVE_POINTER_KEYS = {
    "schema_version",
    "artifact_kind",
    "status",
    "retirement",
    "previous_pointer",
    "snapshot",
    "task_id",
    "task_sha256",
    "publication",
}


def inactive_pointer(root: Path) -> tuple[dict[str, Any], str] | None:
    body = read_current_bytes(root)
    if body is None:
        return None
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or set(value) != INACTIVE_POINTER_KEYS:
        return None
    if (
        value.get("schema_version") != 2
        or value.get("artifact_kind") != "terminal_wait_baseline_current"
        or value.get("status") != "inactive"
    ):
        return None
    reopened: dict[str, dict[str, Any]] = {}
    for field in ("retirement", "previous_pointer", "snapshot", "publication"):
        binding = value.get(field)
        if not isinstance(binding, dict) or set(binding) != {"ref", "sha256"}:
            raise ValueError("inactive terminal-wait pointer binding is malformed")
        _, reopened[field] = read_bound_json(
            root, binding, f"inactive terminal-wait {field}"
        )
    retirement = reopened["retirement"]
    previous = reopened["previous_pointer"]
    snapshot = reopened["snapshot"]
    snapshot_task = snapshot.get("task") if isinstance(snapshot, dict) else None
    if (
        retirement.get("artifact_kind") != "terminal_wait_baseline_retirement"
        or retirement.get("status") != "retired"
        or retirement.get("previous_pointer") != value["previous_pointer"]
        or retirement.get("snapshot") != value["snapshot"]
        or retirement.get("publication") != value["publication"]
        or previous.get("task_id") != value["task_id"]
        or previous.get("task_sha256") != value["task_sha256"]
        or not isinstance(snapshot_task, dict)
        or snapshot_task.get("task_id") != value["task_id"]
        or snapshot_task.get("sha256") != value["task_sha256"]
    ):
        raise ValueError("inactive terminal-wait pointer history is inconsistent")
    return value, sha256_bytes(body)


def active_current_pointer(
    root: Path, *, require_current_task: bool
) -> tuple[dict[str, Any], str, dict[str, Any]] | None:
    if inactive_pointer(root) is not None:
        return None
    return load_current_pointer(root, require_current_task=require_current_task)


def _validated_successor(
    root: Path,
    pointer: dict[str, Any],
    publication_binding: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    from .selection_publication import (
        _committed_receipts,
        publication_status,
        validate_receipt,
    )
    from .selection_publication_v2 import validate_external_settlement_assertion

    _, publication_raw = read_bound_json(
        root, publication_binding, "selection publication retirement receipt"
    )
    transaction_id = publication_raw.get("transaction_id")
    if not isinstance(transaction_id, str):
        raise ValueError("selection publication retirement transaction is invalid")
    publication = validate_receipt(root, transaction_id, require_current_targets=True)
    if (
        publication.get("receipt_ref") != publication_binding.get("ref")
        or publication.get("receipt_sha256") != publication_binding.get("sha256")
    ):
        raise ValueError("selection publication retirement binding differs")
    targets = publication.get("targets")
    target = targets[0] if isinstance(targets, list) and len(targets) == 1 else {}
    after = target.get("after_sha256")
    if (
        target.get("role") != "task_alias"
        or target.get("target_ref") != "task.md"
        or target.get("before_sha256") != pointer.get("task_sha256")
        or not isinstance(after, str)
    ):
        raise ValueError("selection publication is not the baseline successor")
    matches = [
        receipt
        for receipt in _committed_receipts(root)
        for row in receipt.get("targets", [])
        if isinstance(row, dict)
        and row.get("role") == "task_alias"
        and row.get("before_sha256") == pointer.get("task_sha256")
        and row.get("after_sha256") == after
    ]
    if len(matches) != 1 or matches[0]["transaction_id"] != transaction_id:
        raise ValueError("terminal-wait baseline successor publication is ambiguous")
    if publication.get("schema_version") == 3:
        if not publication_status(root).get("selection_consumption_allowed"):
            raise ValueError(
                "task-state external settlement is required before retirement"
            )
        validate_external_settlement_assertion(
            root, publication_raw, publication_binding
        )
    return publication, publication_raw, after


def retire_terminal_wait_baseline(
    root: Path, publication_binding: dict[str, str]
) -> dict[str, Any]:
    """Retire a stale active baseline through one exact committed successor."""

    root = root.expanduser().resolve(strict=True)
    with mutation_lock(root):
        inactive = inactive_pointer(root)
        if inactive is not None:
            pointer, digest = inactive
            if pointer["publication"] != publication_binding:
                raise ValueError("terminal-wait baseline has another retirement")
            return {
                "status": "inactive",
                "mutation_performed": False,
                "idempotent": True,
                "retirement": pointer["retirement"],
                "current_pointer": {
                    "ref": ".task/terminal_wait_baseline/current.json",
                    "sha256": digest,
                },
            }
        raw = read_current_bytes(root)
        if raw is None:
            raise ValueError("terminal-wait baseline has no active pointer to retire")
        try:
            pointer = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("terminal-wait baseline current pointer is malformed") from exc
        if not isinstance(pointer, dict) or set(pointer) != POINTER_KEYS:
            raise ValueError("terminal-wait baseline active pointer contract is invalid")
        snapshot_binding = pointer.get("snapshot")
        _, snapshot = read_bound_json(
            root, snapshot_binding, "terminal-wait baseline retirement snapshot"
        )
        task = snapshot.get("task") if isinstance(snapshot, dict) else None
        if (
            not isinstance(task, dict)
            or task.get("task_id") != pointer.get("task_id")
            or task.get("sha256") != pointer.get("task_sha256")
        ):
            raise ValueError("terminal-wait baseline pointer/snapshot task mismatch")
        _publication, _publication_raw, after = _validated_successor(
            root, pointer, publication_binding
        )
        previous_binding = write_once(
            root, "pointers", sha256_bytes(raw), raw
        )
        core = {
            "schema_version": 2,
            "artifact_kind": "terminal_wait_baseline_retirement",
            "status": "retired",
            "previous_pointer": previous_binding,
            "snapshot": snapshot_binding,
            "publication": publication_binding,
            "task_alias_before_sha256": pointer["task_sha256"],
            "task_alias_after_sha256": after,
        }
        retirement_id = "twbr-" + sha256_bytes(display_bytes(core))[:32]
        retirement_binding = write_once(
            root,
            "retirements",
            retirement_id,
            display_bytes({**core, "retirement_id": retirement_id}),
        )
        inactive_body = {
            "schema_version": 2,
            "artifact_kind": "terminal_wait_baseline_current",
            "status": "inactive",
            "retirement": retirement_binding,
            "previous_pointer": previous_binding,
            "snapshot": snapshot_binding,
            "task_id": pointer["task_id"],
            "task_sha256": pointer["task_sha256"],
            "publication": publication_binding,
        }
        current_binding = write_current(root, display_bytes(inactive_body))
        verified = inactive_pointer(root)
        if verified is None:
            raise ValueError("terminal-wait baseline retirement did not verify")
        return {
            "status": "inactive",
            "mutation_performed": True,
            "idempotent": False,
            "retirement": retirement_binding,
            "previous_pointer": previous_binding,
            "current_pointer": current_binding,
            "publication": publication_binding,
        }


__all__ = (
    "active_current_pointer",
    "inactive_pointer",
    "retire_terminal_wait_baseline",
)
