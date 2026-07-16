from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .common import boolish, first_present, list_values, value_for

def _positive_decision_claim(target: str, result: dict[str, Any]) -> bool:
    validation_verdict = str(value_for(result, "validation_verdict") or "").strip().lower()
    review_status = str(value_for(result, "review_status") or "").strip().lower()
    quality_verdict = str(value_for(result, "quality_verdict") or "").strip().lower()
    progress_verdict = str(value_for(result, "progress_verdict") or "").strip().lower()
    progress_kind = str(value_for(result, "progress_kind") or "").strip().lower()
    completion_status = str(first_present(result, ["completion_status", "report.completion_status", "result.completion_status"]) or "").strip().lower()
    pack_transition_status = str(
        first_present(result, ["pack_transition_verdict.status", "pack_transition_status", "result.pack_transition_verdict.status"])
        or ""
    ).strip().lower()
    return bool(
        (target == "validate" and validation_verdict in {"complete", "pass", "passed", "success"})
        or (target == "qualitative_review" and review_status == "complete" and quality_verdict == "acceptable")
        or completion_status in {"complete", "complete_verified", "closed", "promoted"}
        or pack_transition_status in {"pass", "passed", "promoted", "complete"}
        or boolish(first_present(result, ["pack_transition_applied", "successor_auto_promoted", "promotion_applied"]))
        or progress_verdict == "advanced"
        or progress_kind == "goal_productive"
        or boolish(first_present(result, ["semantic_progress", "authoritative_semantic_progress"]))
        or boolish(first_present(result, ["hard_stop_required", "hard_stop"]))
    )


def _full_sha256(value: Any) -> bool:
    normalized = str(value or "").strip().lower().removeprefix("sha256:")
    return len(normalized) == 64 and all(character in "0123456789abcdef" for character in normalized)


def _opaque_scalar(value: Any, *, max_length: int = 256) -> bool:
    return bool(
        isinstance(value, str)
        and 0 < len(value.strip()) <= max_length
        and not any(ord(character) < 32 or ord(character) == 127 for character in value.strip())
    )


def _opaque_string_items(value: Any) -> tuple[list[str], bool]:
    if value is None:
        return [], True
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return [], False
    items = [item.strip() for item in value if _opaque_scalar(item)]
    return items, len(items) == len(value)


def _finite_numeric(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _declared_values(data: dict[str, Any], paths: tuple[str, ...]) -> list[Any]:
    values: list[Any] = []
    for path in paths:
        current: Any = data
        declared = True
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                declared = False
                break
            current = current[part]
        if declared:
            values.append(current)
    return values


def _normalized_verdict_status(value: Any) -> str:
    if isinstance(value, dict):
        raw = value.get("status") if value.get("status") is not None else value.get("verdict")
    else:
        raw = value
    status = str(raw or "").strip().lower()
    if status in {"", "missing", "unknown", "unobserved"}:
        return "not_evaluated"
    return status


def _consumer_receipt_pass(
    row: dict[str, Any],
    bool_field: str,
    status_field: str,
) -> bool:
    if bool_field in row:
        return boolish(row.get(bool_field))
    return str(row.get(status_field) or "").strip().lower() in {
        "pass",
        "passed",
        "complete",
        "completed",
        "consumed",
        "success",
    }


def _consumer_receipt_binding_sha256(row: dict[str, Any]) -> str:
    basis = {
        "consumer_context_id": str(row.get("consumer_context_id") or ""),
        "cycle_id": str(row.get("cycle_id") or ""),
        "input_state_fingerprint": str(row.get("input_state_fingerprint") or ""),
        "attempt_identity": str(row.get("attempt_identity") or ""),
        "artifact_id": row.get("artifact_id"),
        "artifact_sha256": row.get("artifact_sha256"),
        "production_lane_identity": row.get("production_lane_identity"),
        "body_projection_fingerprint": row.get("body_projection_fingerprint"),
        "verification_input_ids": sorted(
            str(item) for item in list_values(row.get("verification_input_ids"))
        ),
        "input_fingerprints": (
            row.get("input_fingerprints")
            if isinstance(row.get("input_fingerprints"), dict)
            else None
        ),
        "evidence_provenance": str(row.get("evidence_provenance") or "").strip().lower(),
        "adapter_loaded": boolish(row.get("adapter_loaded")),
        "hook_resolved": boolish(
            row.get("hook_resolved")
            if "hook_resolved" in row
            else row.get("required_hook_callable")
        ),
        "required_hook_callable": boolish(row.get("required_hook_callable")),
        "hook_signature_compatible": boolish(row.get("hook_signature_compatible")),
        "invocation_completed": _consumer_receipt_pass(
            row,
            "invocation_completed",
            "invocation_status",
        ),
        "return_contract_valid": boolish(row.get("return_contract_valid")),
        "artifact_identity_echo_valid": _consumer_receipt_pass(
            row,
            "artifact_identity_echo_valid",
            "artifact_identity_echo_status",
        ),
        "value_consumed_by_decision": _consumer_receipt_pass(
            row,
            "value_consumed_by_decision",
            "decision_consumption_status",
        ),
        "probe_evidence_ref": str(row.get("probe_evidence_ref") or ""),
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _metric_gate_signature(gate: Any) -> tuple[Any, ...]:
    if not isinstance(gate, dict):
        return ("invalid_gate",)
    raw_status = gate.get("evaluation_status") if gate.get("evaluation_status") is not None else gate.get("status")
    status = raw_status.strip().lower() if isinstance(raw_status, str) else "invalid_contract"
    improved, improved_valid = _opaque_string_items(gate.get("improved_fields"))
    summaries: list[tuple[str, tuple[str, ...], bool]] = []
    for field in ("not_applicable_fields", "insufficient_evidence_fields", "invalid_contract_fields"):
        items, valid = _opaque_string_items(gate.get(field))
        summaries.append((field, tuple(sorted(set(items))), valid))
    policy = gate.get("quality_delta_policy")
    policy_signature: tuple[Any, ...] = ("missing",)
    if isinstance(policy, dict):
        declared_value = policy.get("declared_keys") if policy.get("declared_keys") is not None else policy.get("keys")
        declared, declared_valid = _opaque_string_items(declared_value)
        mapping = policy.get("applicability")
        rows: list[tuple[str, str]] = []
        mapping_valid = mapping is None or isinstance(mapping, dict)
        if isinstance(mapping, dict):
            for metric_id, row in mapping.items():
                if not _opaque_scalar(metric_id) or not isinstance(row, dict):
                    mapping_valid = False
                    continue
                raw_row_status = row.get("evaluation_status")
                row_status = raw_row_status.strip().lower() if isinstance(raw_row_status, str) else "invalid_contract"
                rows.append((metric_id.strip(), row_status))
        elif mapping is None:
            rows = [(metric_id, "applicable") for metric_id in declared]
        policy_signature = (
            tuple(sorted(set(declared))),
            declared_valid,
            tuple(sorted(rows)),
            mapping_valid,
            boolish(policy.get("policy_contract_invalid")),
        )
    vectors: list[tuple[str, tuple[tuple[str, str], ...], bool]] = []
    for field in ("current_quality_vector", "previous_high_water_vector", "previous_quality_vector"):
        value = gate.get(field)
        if value is None:
            vectors.append((field, (), True))
            continue
        if not isinstance(value, dict):
            vectors.append((field, (), False))
            continue
        safe: list[tuple[str, str]] = []
        valid = True
        for metric_id, observation in value.items():
            if not _opaque_scalar(metric_id) or not _finite_numeric(observation):
                valid = False
                continue
            safe.append((metric_id.strip(), repr(float(observation))))
        vectors.append((field, tuple(sorted(safe)), valid))
    return (
        status,
        boolish(gate.get("quality_delta_pass")),
        tuple(sorted(set(improved))),
        improved_valid,
        tuple(summaries),
        policy_signature,
        tuple(vectors),
    )

