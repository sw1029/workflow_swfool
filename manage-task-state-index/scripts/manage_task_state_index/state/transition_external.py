"""Prospective task-state activation settled by selection publication."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import load_events_read_only, merge_state
from .render import _markdown_projection_matches
from .selected_successor_guard import require_selected_successor_execution
from .storage import index_lock, rel_path, sha256_file
from .transition_plan_contract import (
    canonical_bytes,
    load_transition_plan,
    owned_transition_file,
    publish_immutable,
    regular_payload,
    sha256_bytes,
    workspace_path,
)
from .transition_recovery import committed_boundary_valid, matching_events


def is_external_plan(plan: dict[str, Any]) -> bool:
    request = plan.get("request")
    return bool(
        plan.get("schema_version") == 2
        and isinstance(request, dict)
        and request.get("schema_version") == 2
        and request.get("external_settlement_kind") == "selection_publication"
    )


def _binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise ValueError(f"{label} requires exactly ref and sha256")
    ref = value.get("ref")
    digest = value.get("sha256")
    if (
        not isinstance(ref, str)
        or not ref
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{label} binding is invalid")
    return {"ref": ref, "sha256": digest}


def _read_bound_json(
    root: Path, value: Any, label: str
) -> tuple[dict[str, str], dict[str, Any]]:
    binding = _binding(value, label)
    path = workspace_path(root, binding["ref"])
    payload = regular_payload(path)
    if sha256_bytes(payload) != binding["sha256"]:
        raise ValueError(f"{label} bytes differ from their binding")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not a JSON object") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} is not a JSON object")
    return binding, decoded


def _task_source(plan: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    rows = plan["request"]["artifact_sources"]
    matches = [row for row in rows if row.get("target_ref") == "task.md"]
    anchors = [row for row in plan["artifact_anchors"] if row.get("path") == "task.md"]
    if len(matches) != 1 or len(anchors) != 1:
        raise ValueError("External transition requires one prospective task.md source")
    return matches[0]["source"], anchors[0]


def validate_external_prepare(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
    value: Any,
) -> dict[str, str]:
    if not is_external_plan(plan):
        raise ValueError("Task-state plan does not use external settlement")
    binding, prepare = _read_bound_json(root, value, "selection publication prepare")
    transaction_id = prepare.get("transaction_id")
    expected_ref = (
        f".task/selection_publication/transactions/{transaction_id}/prepare.json"
    )
    source, anchor = _task_source(plan)
    targets = prepare.get("targets")
    target = targets[0] if isinstance(targets, list) and len(targets) == 1 else {}
    if (
        prepare.get("schema_version") != 3
        or prepare.get("kind") != "selection_publication_prepare"
        or binding["ref"] != expected_ref
        or prepare.get("task_state_plan")
        != {"ref": plan_ref, "sha256": plan_file_sha256}
        or target.get("role") != "task_alias"
        or target.get("target_ref") != "task.md"
        or target.get("before_sha256") != anchor["before_sha256"]
        or target.get("after_sha256") != source["sha256"]
        or target.get("payload_sha256") != source["sha256"]
    ):
        raise ValueError("Selection publication prepare does not bind the prospective plan")
    return binding


def pending_receipt_for_plan(
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
    external_prepare: dict[str, str],
) -> dict[str, Any]:
    body = {
        "schema_version": 2,
        "receipt_kind": "task_state_transition_pending_receipt",
        "activation_status": "pending_external_settlement",
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "applied_at": plan["created_at"],
        "ledger_after_sha256": plan["ledger"]["after_sha256"],
        "markdown_after_sha256": plan["markdown"]["after_sha256"],
        "event_count": plan["ledger"]["event_count"],
        "external_prepare": external_prepare,
    }
    return {**body, "receipt_content_sha256": sha256_bytes(canonical_bytes(body))}


def pending_receipt_path(root: Path, plan_id: str, *, create: bool) -> Path:
    return owned_transition_file(
        root,
        "transition_pending_receipts",
        f"{plan_id}.json",
        create_parent=create,
    )


def publish_pending_receipt(
    root: Path, plan: dict[str, Any], receipt: dict[str, Any]
) -> tuple[Path, bool, str]:
    path = pending_receipt_path(root, str(plan["plan_id"]), create=True)
    payload = canonical_bytes(receipt) + b"\n"
    created = publish_immutable(path, payload)
    return path, created, sha256_bytes(payload)


def load_pending_receipt(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    path = pending_receipt_path(root, str(plan["plan_id"]), create=False)
    payload = regular_payload(path)
    try:
        receipt = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Task-state pending receipt is unreadable") from exc
    if not isinstance(receipt, dict):
        raise ValueError("Task-state pending receipt is invalid")
    external_prepare = _binding(
        receipt.get("external_prepare"), "task-state external prepare"
    )
    expected = pending_receipt_for_plan(
        plan, plan_ref, plan_file_sha256, external_prepare
    )
    if receipt != expected or payload != canonical_bytes(receipt) + b"\n":
        raise ValueError("Task-state pending receipt integrity mismatch")
    return receipt, {"ref": rel_path(root, path), "sha256": sha256_bytes(payload)}


def _settled_receipt(
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
    pending: dict[str, str],
    external_prepare: dict[str, str],
    external_commit: dict[str, str],
) -> dict[str, Any]:
    body = {
        "schema_version": 2,
        "receipt_kind": "task_state_transition_apply_receipt",
        "activation_status": "settled",
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "applied_at": plan["created_at"],
        "ledger_after_sha256": plan["ledger"]["after_sha256"],
        "markdown_after_sha256": plan["markdown"]["after_sha256"],
        "event_count": plan["ledger"]["event_count"],
        "pending_receipt": pending,
        "external_prepare": external_prepare,
        "external_commit": external_commit,
    }
    return {**body, "receipt_content_sha256": sha256_bytes(canonical_bytes(body))}


def settled_receipt_for_plan(
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
    pending: dict[str, str],
    external_prepare: dict[str, str],
    external_commit: dict[str, str],
) -> dict[str, Any]:
    """Pure public renderer for an exact externally settled receipt."""

    return _settled_receipt(
        plan, plan_ref, plan_file_sha256, pending, external_prepare, external_commit
    )


def external_receipt_binding(
    plan: dict[str, Any], receipt: dict[str, Any], *, pending: bool = False
) -> dict[str, str]:
    """Predict the canonical raw-file binding for a rendered external receipt."""

    directory = "transition_pending_receipts" if pending else "transition_receipts"
    return {
        "ref": f".task/{directory}/{plan['plan_id']}.json",
        "sha256": sha256_bytes(canonical_bytes(receipt) + b"\n"),
    }


def settled_receipt_status(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> tuple[str, str | None]:
    path = owned_transition_file(
        root,
        "transition_receipts",
        f"{plan['plan_id']}.json",
        create_parent=False,
    )
    if not path.exists() and not path.is_symlink():
        return "missing", None
    try:
        payload = regular_payload(path)
        receipt = json.loads(payload)
        if not isinstance(receipt, dict):
            return "conflict", sha256_bytes(payload)
        pending = _binding(receipt.get("pending_receipt"), "pending receipt")
        prepare = _binding(receipt.get("external_prepare"), "external prepare")
        commit = _binding(receipt.get("external_commit"), "external commit")
        expected = _settled_receipt(
            plan, plan_ref, plan_file_sha256, pending, prepare, commit
        )
        if receipt != expected or payload != canonical_bytes(receipt) + b"\n":
            return "conflict", sha256_bytes(payload)
        _pending, observed_pending = load_pending_receipt(
            root, plan, plan_ref, plan_file_sha256
        )
        if observed_pending != pending:
            return "conflict", sha256_bytes(payload)
        _validate_publication_commit(root, plan, pending, prepare, commit)
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return "conflict", sha256_file(path)
    return "current", sha256_bytes(payload)


def _validate_publication_commit(
    root: Path,
    plan: dict[str, Any],
    pending_binding: dict[str, str],
    prepare_binding: dict[str, str],
    commit_value: Any,
) -> dict[str, str]:
    binding, receipt = _read_bound_json(root, commit_value, "selection publication receipt")
    source, anchor = _task_source(plan)
    targets = receipt.get("targets")
    target = targets[0] if isinstance(targets, list) and len(targets) == 1 else {}
    if (
        receipt.get("schema_version") != 3
        or receipt.get("kind") != "selection_publication_receipt"
        or receipt.get("status") != "committed"
        or receipt.get("prepare_ref") != prepare_binding["ref"]
        or receipt.get("prepare_sha256") != prepare_binding["sha256"]
        or receipt.get("external_settlement_plan_id") != plan["plan_id"]
        or receipt.get("owner_pending_receipt") != pending_binding
        or target.get("role") != "task_alias"
        or target.get("target_ref") != "task.md"
        or target.get("before_sha256") != anchor["before_sha256"]
        or target.get("after_sha256") != source["sha256"]
        or sha256_file(workspace_path(root, "task.md")) != source["sha256"]
    ):
        raise ValueError("Selection publication receipt does not settle the task-state plan")
    return binding


def settle_external_transition(
    root: Path,
    path_value: str | Path,
    external_commit_value: Any,
    *,
    _selected_successor_execution_token: object | None = None,
) -> dict[str, Any]:
    require_selected_successor_execution(_selected_successor_execution_token)
    root = root.resolve()
    plan_path, plan, plan_file_sha256 = load_transition_plan(root, path_value)
    if not is_external_plan(plan):
        raise ValueError("Task-state transition plan has no external settlement")
    plan_ref = rel_path(root, plan_path)
    created = False
    with index_lock(root):
        pending_receipt, pending_binding = load_pending_receipt(
            root, plan, plan_ref, plan_file_sha256
        )
        commit_binding = _validate_publication_commit(
            root,
            plan,
            pending_binding,
            pending_receipt["external_prepare"],
            external_commit_value,
        )
        events, _ = load_events_read_only(root)
        exact, conflict = matching_events(events, plan)
        if conflict or not exact or not committed_boundary_valid(root, plan, events):
            raise ValueError("Task-state external settlement lacks its exact event batch")
        if not _markdown_projection_matches(root, merge_state(events)):
            raise ValueError("Task-state external settlement projection is stale")
        receipt = _settled_receipt(
            plan,
            plan_ref,
            plan_file_sha256,
            pending_binding,
            pending_receipt["external_prepare"],
            commit_binding,
        )
        path = owned_transition_file(
            root,
            "transition_receipts",
            f"{plan['plan_id']}.json",
            create_parent=True,
        )
        payload = canonical_bytes(receipt) + b"\n"
        created = publish_immutable(path, payload)
        digest = sha256_bytes(payload)
    return {
        "result_kind": "task_state_transition_external_settlement_result",
        "schema_version": 2,
        "status": "settled" if created else "already_settled",
        "activation_status": "active",
        "plan_id": plan["plan_id"],
        "receipt_ref": rel_path(root, path),
        "receipt_file_sha256": digest,
        "execution_result_binding": {"ref": rel_path(root, path), "sha256": digest},
        "selection_consumption_allowed": True,
        "mutation_performed": created,
    }


__all__ = (
    "is_external_plan",
    "load_pending_receipt",
    "pending_receipt_for_plan",
    "publish_pending_receipt",
    "external_receipt_binding",
    "settled_receipt_for_plan",
    "settled_receipt_status",
    "settle_external_transition",
    "validate_external_prepare",
)
