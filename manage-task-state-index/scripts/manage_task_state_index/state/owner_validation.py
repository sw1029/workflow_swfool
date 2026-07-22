"""Public descendant-aware owner-result validation for authority settlement."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import load_events_read_only, merge_state
from .render import _markdown_projection_matches
from .scan_result_integrity import validate_scan_result_evidence
from .scan_transition import load_scan_compilation
from .storage import rel_path, sha256_file
from .transition_external import (
    _settled_receipt,
    _task_source,
    is_external_plan,
    load_pending_receipt,
)
from .transition_no_effect import validate_no_effect_receipt
from .transition_plan_contract import (
    canonical_bytes,
    load_transition_plan,
    regular_payload,
    sha256_bytes,
    workspace_path,
)
from .transition_recovery import committed_boundary_valid, event_payload


PHASES = {"current", "historical"}
RECEIPT_FIELDS = frozenset("""schema_version artifact_kind operation
validation_status outcome owner_result reservation pre_commit_verification phase
subject projection plan event_batch descendant_event_count validated_at
receipt_sha256""".split())


def normalize_binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise ValueError(f"{label} requires exactly ref and sha256")
    ref, digest = value.get("ref"), value.get("sha256")
    if (
        not isinstance(ref, str) or not ref or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{label} binding is invalid")
    return {"ref": ref, "sha256": digest}


def _read_bound(
    root: Path, value: Any, label: str
) -> tuple[dict[str, str], bytes, Any]:
    binding = normalize_binding(value, label)
    path = workspace_path(root, binding["ref"])
    payload = regular_payload(path)
    if sha256_bytes(payload) != binding["sha256"]:
        raise ValueError(f"{label} bytes differ from their binding")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain JSON") from exc
    return binding, payload, decoded


def seal_owner_validation_receipt(body: dict[str, Any]) -> dict[str, Any]:
    """Seal one closed receipt; the digest excludes only receipt_sha256."""

    if set(body) != RECEIPT_FIELDS - {"receipt_sha256"}:
        raise ValueError("Owner validation receipt body fields are not closed")
    return {**body, "receipt_sha256": sha256_bytes(canonical_bytes(body))}


def _plan_batch(
    root: Path, plan: dict[str, Any], events: list[dict[str, Any]]
) -> tuple[dict[str, Any], int]:
    if not committed_boundary_valid(root, plan, events):
        raise ValueError("Task-state owner result lacks a valid committed boundary")
    if not _markdown_projection_matches(root, merge_state(events)):
        raise ValueError("Task-state owner result current projection is stale")
    descendant_count = (
        len(events) - plan["ledger"]["before_event_count"]
        - plan["ledger"]["event_count"]
    )
    return ({
        "plan_id": plan["plan_id"],
        "before_event_count": plan["ledger"]["before_event_count"],
        "event_count": plan["ledger"]["event_count"],
        "event_payload_sha256": sha256_bytes(event_payload(plan["events"])),
    }, descendant_count)


def validate_external_transition_receipt(
    root: Path,
    receipt_binding: dict[str, str],
    *,
    phase: str = "current",
) -> dict[str, Any]:
    """Validate a settled external transition with a legal descendant suffix."""

    if phase not in PHASES:
        raise ValueError("Task-state validation phase must be current or historical")
    root = root.resolve()
    binding, payload, receipt = _read_bound(
        root, receipt_binding, "task-state external transition receipt"
    )
    if not isinstance(receipt, dict):
        raise ValueError("Task-state external transition receipt must be an object")
    plan_path, plan, plan_file_sha256 = load_transition_plan(
        root, str(receipt.get("plan_ref") or "")
    )
    if not is_external_plan(plan):
        raise ValueError("Task-state receipt is not an external transition")
    plan_ref = rel_path(root, plan_path)
    pending_binding = normalize_binding(receipt.get("pending_receipt"), "pending receipt")
    prepare = normalize_binding(receipt.get("external_prepare"), "external prepare")
    commit = normalize_binding(receipt.get("external_commit"), "external commit")
    expected = _settled_receipt(
        plan, plan_ref, plan_file_sha256, pending_binding, prepare, commit
    )
    if receipt != expected or payload != canonical_bytes(receipt) + b"\n":
        raise ValueError("Task-state external transition receipt integrity mismatch")
    pending, observed_pending = load_pending_receipt(
        root, plan, plan_ref, plan_file_sha256
    )
    if observed_pending != pending_binding or pending["external_prepare"] != prepare:
        raise ValueError("Task-state external pending receipt binding mismatch")
    _commit_binding, _commit_payload, commit_value = _read_bound(
        root, commit, "selection publication receipt"
    )
    if (
        not isinstance(commit_value, dict)
        or commit_value.get("schema_version") != 3
        or commit_value.get("kind") != "selection_publication_receipt"
        or commit_value.get("status") != "committed"
        or commit_value.get("prepare_ref") != prepare["ref"]
        or commit_value.get("prepare_sha256") != prepare["sha256"]
        or commit_value.get("external_settlement_plan_id") != plan["plan_id"]
        or commit_value.get("owner_pending_receipt") != pending_binding
    ):
        raise ValueError("Selection publication receipt does not bind the transition")
    source, _anchor = _task_source(plan)
    if phase == "current" and sha256_file(workspace_path(root, "task.md")) != source["sha256"]:
        raise ValueError("Current selected task no longer matches the external transition")
    events, _ = load_events_read_only(root)
    batch, descendants = _plan_batch(root, plan, events)
    if phase == "historical":
        # Historical replay proves the committed boundary and legal suffix, but
        # does not seal the suffix length into the immutable authority receipt.
        descendants = 0
    return {
        "result_kind": "task_state_external_transition_validation_result",
        "schema_version": 1,
        "status": "valid",
        "phase": phase,
        "plan_id": plan["plan_id"],
        "plan_binding": {"ref": plan_ref, "sha256": plan_file_sha256},
        "receipt_binding": binding,
        "effect_status": "confirmed_effect",
        "subject": {
            "kind": "task_index", "ref": ".task/index.jsonl",
            "before_sha256": plan["ledger"]["before_sha256"],
            "after_sha256": plan["ledger"]["after_sha256"],
        },
        "projection": {
            "ref": ".task/index.md",
            "before_sha256": plan["markdown"]["before_sha256"],
            "after_sha256": plan["markdown"]["after_sha256"],
        },
        "event_batch": batch,
        "descendant_event_count": descendants,
        "validated_at": receipt["applied_at"],
        "selection_consumption_allowed": True,
    }


def _validate_scan_result(
    root: Path,
    binding: dict[str, str],
    payload: bytes,
    result: dict[str, Any],
    *,
    phase: str,
) -> dict[str, Any]:
    compilation_binding, compilation = load_scan_compilation(
        root, result.get("compilation")
    )
    if compilation_binding != result["compilation"]:
        raise ValueError("Task-state scan result compilation binding differs")
    checked = validate_scan_result_evidence(
        root, binding, payload, result, compilation_binding, compilation
    )
    descendants = checked["descendant_event_count"]
    if phase == "historical":
        # Keep the replay receipt stable as later append-only descendants land.
        descendants = 0
    return {
        "outcome": checked["effect_status"], "validation_status": "valid",
        "subject": checked["subject"], "projection": checked["projection"],
        "plan": checked["plan"], "event_batch": checked["event_batch"],
        "descendant_event_count": descendants,
        "validated_at": checked["validated_at"], "owner_result": binding,
    }


def _validate_no_effect_result(
    root: Path, binding: dict[str, str], payload: bytes, value: dict[str, Any]
) -> dict[str, Any]:
    plan_path, plan, plan_digest = load_transition_plan(root, value.get("plan_ref", ""))
    validate_no_effect_receipt(value, plan, rel_path(root, plan_path), plan_digest)
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError("Task-state no-effect receipt bytes are not canonical")
    observed = value["observation"]
    empty_batch = {
        "plan_id": plan["plan_id"],
        "before_event_count": plan["ledger"]["before_event_count"],
        "event_count": 0,
        "event_payload_sha256": sha256_bytes(b""),
    }
    return {
        "outcome": "confirmed_no_effect", "validation_status": "valid",
        "subject": {"kind": "task_index", "ref": ".task/index.jsonl",
                    "before_sha256": observed["ledger_sha256"],
                    "after_sha256": observed["ledger_sha256"]},
        "projection": {"ref": ".task/index.md",
                       "before_sha256": observed["markdown_sha256"],
                       "after_sha256": observed["markdown_sha256"]},
        "plan": {"ref": rel_path(root, plan_path), "sha256": plan_digest},
        "event_batch": empty_batch, "descendant_event_count": 0,
        "validated_at": value["settled_at"], "owner_result": binding,
    }


def validate_owner_result(
    root: Path,
    *,
    owner_result: dict[str, str],
    reservation: dict[str, str],
    pre_commit_verification: dict[str, str],
    phase: str = "current",
) -> dict[str, Any]:
    """Return a deterministic closed receipt for authority consume/release/quarantine."""

    if phase not in PHASES:
        raise ValueError("Task-state validation phase must be current or historical")
    root = root.resolve()
    reservation_binding, _reservation_payload, _reservation = _read_bound(
        root, reservation, "authority reservation"
    )
    precommit_binding, _precommit_payload, precommit = _read_bound(
        root, pre_commit_verification, "authority pre-commit verification"
    )
    binding, payload, value = _read_bound(root, owner_result, "owner result")
    if not isinstance(value, dict):
        raise ValueError("Task-state owner result must be a JSON object")
    if value.get("artifact_kind") == "task_state_index_scan_result" and value.get("schema_version") == 2:
        validated = _validate_scan_result(
            root, binding, payload, value, phase=phase
        )
    elif value.get("receipt_kind") == "task_state_transition_apply_receipt" and value.get("activation_status") == "settled":
        external = validate_external_transition_receipt(root, binding, phase=phase)
        validated = {
            "outcome": "confirmed_effect", "validation_status": "valid",
            "subject": external["subject"], "projection": external["projection"],
            "plan": external["plan_binding"], "event_batch": external["event_batch"],
            "descendant_event_count": external["descendant_event_count"],
            "validated_at": external["validated_at"], "owner_result": binding,
        }
    elif value.get("receipt_kind") == "task_state_transition_no_effect_receipt":
        validated = _validate_no_effect_result(root, binding, payload, value)
    else:
        subject = value.get("subject") if isinstance(value.get("subject"), dict) else None
        projection = value.get("projection") if isinstance(value.get("projection"), dict) else None
        validated = {
            "outcome": "unknown_effect", "validation_status": "legacy_opaque",
            "subject": subject, "projection": projection, "plan": None,
            "event_batch": None, "descendant_event_count": 0,
            "validated_at": value.get("completed_at")
            or (precommit.get("verified_at") if isinstance(precommit, dict) else None),
            "owner_result": binding,
        }
    body = {
        "schema_version": 1,
        "artifact_kind": "owner_validation_receipt",
        "operation": "mutate_task_state_index",
        "validation_status": validated["validation_status"],
        "outcome": validated["outcome"],
        "owner_result": validated["owner_result"],
        "reservation": reservation_binding,
        "pre_commit_verification": precommit_binding,
        "phase": phase,
        "subject": validated["subject"],
        "projection": validated["projection"],
        "plan": validated["plan"],
        "event_batch": validated["event_batch"],
        "descendant_event_count": validated["descendant_event_count"],
        "validated_at": validated["validated_at"],
    }
    return seal_owner_validation_receipt(body)


__all__ = (
    "normalize_binding", "seal_owner_validation_receipt",
    "validate_external_transition_receipt", "validate_owner_result",
)
