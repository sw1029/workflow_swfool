"""Reopen terminal-wait baseline artifacts and their authority settlement."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .authority_artifacts import validate_authority_use_receipt_settlement
from .terminal_wait_baseline_build import (
    activation_body,
    pointer_body,
    predict_artifacts,
)
from .terminal_wait_baseline_contract import (
    binding,
    normalize_plan,
    validate_sources,
)
from .terminal_wait_baseline_store import (
    STORE_REF,
    artifact_ref,
    read_bound_json,
    read_current_bytes,
    sha256_bytes,
)


PREPARE_KEYS = {
    "schema_version",
    "artifact_kind",
    "transaction_id",
    "plan",
    "snapshot",
}
SNAPSHOT_KEYS = {
    "schema_version",
    "artifact_kind",
    "binding_id",
    "task",
    "source_derive",
    "transition_evidence",
    "selection_baseline",
    "authority_subject",
    "predecessor_snapshot_sha256",
}
COMPLETION_KEYS = {
    "schema_version",
    "artifact_kind",
    "transaction_id",
    "status",
    "prepare",
    "snapshot",
    "task",
    "completed_at",
}
ACTIVATION_KEYS = {
    "schema_version",
    "artifact_kind",
    "activation_id",
    "completion",
    "snapshot",
    "authority_use_receipt",
    "predecessor_snapshot_sha256",
    "activated_at",
}
POINTER_KEYS = {
    "schema_version",
    "artifact_kind",
    "activation",
    "completion",
    "snapshot",
    "binding_id",
    "task_id",
    "task_sha256",
    "predecessor_snapshot_sha256",
    "authority_use_receipt",
}


def _closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} requires exact fields {sorted(keys)}")
    return value


def load_prepare(
    root: Path,
    artifact_binding: dict[str, str],
    *,
    require_current_task: bool,
    allow_legacy_selection_v1: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    transaction_id = Path(artifact_binding["ref"]).stem
    _, prepare = read_bound_json(
        root,
        artifact_binding,
        "terminal-wait baseline prepare",
        expected_prefix=f"{STORE_REF}/prepares",
        expected_ref=artifact_ref("prepares", transaction_id),
    )
    _closed(prepare, PREPARE_KEYS, "terminal-wait baseline prepare")
    plan = normalize_plan(prepare.get("plan"))
    packet, packet_projection = validate_sources(
        root,
        plan,
        require_current_task=require_current_task,
        allow_legacy_selection_v1=allow_legacy_selection_v1,
    )
    predicted = predict_artifacts(plan, packet_projection)
    if (
        prepare.get("schema_version") != 1
        or prepare.get("artifact_kind") != "terminal_wait_baseline_prepare"
        or prepare.get("transaction_id") != transaction_id
        or transaction_id != predicted["transaction_id"]
        or prepare != predicted["prepare"]
    ):
        raise ValueError("terminal-wait baseline prepare identity is invalid")
    return prepare, plan, packet


def validate_snapshot_binding(
    root: Path,
    artifact_binding: dict[str, str],
    plan: dict[str, Any],
    *,
    require_current_task: bool,
    allow_legacy_selection_v1: bool = False,
) -> dict[str, Any]:
    snapshot_sha256 = artifact_binding["sha256"]
    if Path(artifact_binding["ref"]).stem != snapshot_sha256:
        raise ValueError("terminal-wait snapshot path is not content-addressed")
    _, snapshot = read_bound_json(
        root,
        artifact_binding,
        "terminal-wait baseline snapshot",
        expected_prefix=f"{STORE_REF}/snapshots",
        expected_ref=artifact_ref("snapshots", snapshot_sha256),
    )
    _closed(snapshot, SNAPSHOT_KEYS, "terminal-wait baseline snapshot")
    _, packet_projection = validate_sources(
        root,
        plan,
        require_current_task=require_current_task,
        allow_legacy_selection_v1=allow_legacy_selection_v1,
    )
    expected = predict_artifacts(plan, packet_projection)["snapshot"]
    if snapshot != expected:
        raise ValueError("terminal-wait baseline snapshot differs from its plan")
    return snapshot


def validate_completion_binding(
    root: Path,
    artifact_binding: dict[str, str],
    *,
    require_current_task: bool = True,
    allow_legacy_selection_v1: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    transaction_id = Path(artifact_binding["ref"]).stem
    _, completion = read_bound_json(
        root,
        artifact_binding,
        "terminal-wait baseline completion",
        expected_prefix=f"{STORE_REF}/completions",
        expected_ref=artifact_ref("completions", transaction_id),
    )
    _closed(completion, COMPLETION_KEYS, "terminal-wait baseline completion")
    prepare_binding = binding(completion.get("prepare"), "completion.prepare")
    _, plan, _ = load_prepare(
        root,
        prepare_binding,
        require_current_task=require_current_task,
        allow_legacy_selection_v1=allow_legacy_selection_v1,
    )
    snapshot_binding = binding(completion.get("snapshot"), "completion.snapshot")
    snapshot = validate_snapshot_binding(
        root,
        snapshot_binding,
        plan,
        require_current_task=require_current_task,
        allow_legacy_selection_v1=allow_legacy_selection_v1,
    )
    _, packet_projection = validate_sources(
        root,
        plan,
        require_current_task=require_current_task,
        allow_legacy_selection_v1=allow_legacy_selection_v1,
    )
    predicted = predict_artifacts(plan, packet_projection)
    if (
        completion.get("schema_version") != 1
        or completion.get("artifact_kind") != "terminal_wait_baseline_completion"
        or completion.get("transaction_id") != transaction_id
        or completion.get("status") != "committed"
        or completion != predicted["completion"]
        or artifact_binding != predicted["completion_binding"]
    ):
        raise ValueError("terminal-wait baseline completion identity is invalid")
    return completion, snapshot, plan


def validate_activation_binding(
    root: Path,
    artifact_binding: dict[str, str],
    *,
    phase: str,
    require_current_task: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    activation_id = Path(artifact_binding["ref"]).stem
    _, activation = read_bound_json(
        root,
        artifact_binding,
        "terminal-wait baseline activation",
        expected_prefix=f"{STORE_REF}/activations",
        expected_ref=artifact_ref("activations", activation_id),
    )
    _closed(activation, ACTIVATION_KEYS, "terminal-wait baseline activation")
    completion_binding = binding(activation.get("completion"), "activation.completion")
    completion, snapshot, plan = validate_completion_binding(
        root,
        completion_binding,
        require_current_task=require_current_task,
        allow_legacy_selection_v1=phase == "historical",
    )
    use_binding = binding(
        activation.get("authority_use_receipt"), "activation.authority_use_receipt"
    )
    _, use_receipt = read_bound_json(
        root,
        use_binding,
        "authority use receipt",
        expected_prefix=".task/authorization/use_receipts",
    )
    expected = activation_body(
        completion_binding,
        completion["snapshot"],
        use_binding,
        plan["expected_current_snapshot_sha256"],
        use_receipt.get("consumed_at"),
    )
    if activation != expected or activation_id != expected["activation_id"]:
        raise ValueError("terminal-wait baseline activation identity is invalid")
    _, packet = read_bound_json(root, plan["authority_packet"], "authority packet")
    findings = validate_authority_use_receipt_settlement(
        packet,
        use_binding,
        root,
        execution_result=completion_binding,
        idempotency_key=plan["consume_idempotency_key"],
        phase=phase,
    )
    if findings:
        codes = ", ".join(str(row.get("code")) for row in findings)
        raise ValueError(f"authority settlement validation failed: {codes}")
    return activation, snapshot, plan


def load_current_pointer(
    root: Path, *, require_current_task: bool
) -> tuple[dict[str, Any], str, dict[str, Any]] | None:
    body = read_current_bytes(root)
    if body is None:
        return None
    try:
        pointer = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("terminal-wait baseline current pointer is malformed") from exc
    _closed(pointer, POINTER_KEYS, "terminal-wait baseline current pointer")
    activation_binding = binding(pointer.get("activation"), "pointer.activation")
    activation, snapshot, _ = validate_activation_binding(
        root,
        activation_binding,
        phase="historical",
        require_current_task=require_current_task,
    )
    expected = pointer_body(
        activation_binding,
        activation["completion"],
        activation["snapshot"],
        snapshot,
        activation["authority_use_receipt"],
    )
    if pointer != expected:
        raise ValueError("terminal-wait baseline current pointer binding is invalid")
    return pointer, sha256_bytes(body), snapshot


__all__ = (
    "load_current_pointer",
    "load_prepare",
    "validate_activation_binding",
    "validate_completion_binding",
    "validate_snapshot_binding",
)
