"""Pure artifacts for authority-settled terminal-wait baseline publication."""

from __future__ import annotations

from typing import Any

from .terminal_wait_baseline_store import (
    artifact_ref,
    canonical_sha256,
    display_bytes,
    sha256_bytes,
)


def snapshot_body(
    plan: dict[str, Any], packet_projection: dict[str, str]
) -> dict[str, Any]:
    core = {
        "schema_version": 1,
        "artifact_kind": "terminal_wait_selection_baseline_binding",
        "task": plan["task"],
        "source_derive": plan["source_derive"],
        "transition_evidence": plan["transition_evidence"],
        "selection_baseline": {
            **plan["selection_baseline"],
            **packet_projection,
        },
        "authority_subject": plan["authority_subject"],
        "predecessor_snapshot_sha256": plan["expected_current_snapshot_sha256"],
    }
    return {**core, "binding_id": "twbb-" + canonical_sha256(core)[:32]}


def prepare_body(
    plan: dict[str, Any], transaction_id: str, snapshot: dict[str, str]
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "terminal_wait_baseline_prepare",
        "transaction_id": transaction_id,
        "plan": plan,
        "snapshot": snapshot,
    }


def completion_body(
    plan: dict[str, Any],
    transaction_id: str,
    prepare: dict[str, str],
    snapshot: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "terminal_wait_baseline_completion",
        "transaction_id": transaction_id,
        "status": "committed",
        "prepare": prepare,
        "snapshot": snapshot,
        "task": {
            "task_id": plan["task"]["task_id"],
            "sha256": plan["task"]["sha256"],
        },
        "completed_at": plan["prepared_at"],
    }


def predict_artifacts(
    plan: dict[str, Any], packet_projection: dict[str, str]
) -> dict[str, Any]:
    transaction_id = "twbp-" + canonical_sha256(plan)[:32]
    snapshot = snapshot_body(plan, packet_projection)
    snapshot_body_bytes = display_bytes(snapshot)
    snapshot_sha256 = sha256_bytes(snapshot_body_bytes)
    snapshot_binding = {
        "ref": artifact_ref("snapshots", snapshot_sha256),
        "sha256": snapshot_sha256,
    }
    prepare = prepare_body(plan, transaction_id, snapshot_binding)
    prepare_binding = {
        "ref": artifact_ref("prepares", transaction_id),
        "sha256": sha256_bytes(display_bytes(prepare)),
    }
    completion = completion_body(
        plan, transaction_id, prepare_binding, snapshot_binding
    )
    return {
        "transaction_id": transaction_id,
        "snapshot": snapshot,
        "snapshot_body": snapshot_body_bytes,
        "snapshot_binding": snapshot_binding,
        "prepare": prepare,
        "prepare_binding": prepare_binding,
        "completion": completion,
        "completion_binding": {
            "ref": artifact_ref("completions", transaction_id),
            "sha256": sha256_bytes(display_bytes(completion)),
        },
    }


def activation_body(
    completion: dict[str, str],
    snapshot: dict[str, str],
    use_receipt: dict[str, str],
    predecessor_snapshot_sha256: str | None,
    activated_at: str,
) -> dict[str, Any]:
    if not isinstance(activated_at, str) or not activated_at:
        raise ValueError("terminal-wait activation requires a string consumption time")
    core = {
        "schema_version": 1,
        "artifact_kind": "terminal_wait_baseline_activation",
        "completion": completion,
        "snapshot": snapshot,
        "authority_use_receipt": use_receipt,
        "predecessor_snapshot_sha256": predecessor_snapshot_sha256,
        "activated_at": activated_at,
    }
    return {**core, "activation_id": "twba-" + canonical_sha256(core)[:32]}


def pointer_body(
    activation: dict[str, str],
    completion: dict[str, str],
    snapshot_binding: dict[str, str],
    snapshot: dict[str, Any],
    use_receipt: dict[str, str],
) -> dict[str, Any]:
    task = snapshot["task"]
    return {
        "schema_version": 1,
        "artifact_kind": "terminal_wait_baseline_current",
        "activation": activation,
        "completion": completion,
        "snapshot": snapshot_binding,
        "binding_id": snapshot["binding_id"],
        "task_id": task["task_id"],
        "task_sha256": task["sha256"],
        "predecessor_snapshot_sha256": snapshot["predecessor_snapshot_sha256"],
        "authority_use_receipt": use_receipt,
    }


__all__ = (
    "activation_body",
    "pointer_body",
    "predict_artifacts",
    "snapshot_body",
)
