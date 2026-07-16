from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from . import values as _values
from . import vectors as _vectors

def consumer_receipt_pass(
    row: dict[str, Any],
    bool_field: str,
    status_field: str,
) -> bool:
    if bool_field in row:
        return _values.bool_value(row.get(bool_field))
    return str(row.get(status_field) or "").strip().lower() in {
        "pass",
        "passed",
        "complete",
        "completed",
        "consumed",
        "success",
    }

def consumer_receipt_binding_sha256(row: dict[str, Any]) -> str:
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
            str(item) for item in _vectors.string_list(row.get("verification_input_ids"))
        ),
        "input_fingerprints": (
            row.get("input_fingerprints")
            if isinstance(row.get("input_fingerprints"), dict)
            else None
        ),
        "evidence_provenance": str(row.get("evidence_provenance") or "").strip().lower(),
        "adapter_loaded": _values.bool_value(row.get("adapter_loaded")),
        "hook_resolved": _values.bool_value(
            row.get("hook_resolved")
            if "hook_resolved" in row
            else row.get("required_hook_callable")
        ),
        "required_hook_callable": _values.bool_value(row.get("required_hook_callable")),
        "hook_signature_compatible": _values.bool_value(row.get("hook_signature_compatible")),
        "invocation_completed": consumer_receipt_pass(
            row,
            "invocation_completed",
            "invocation_status",
        ),
        "return_contract_valid": _values.bool_value(row.get("return_contract_valid")),
        "artifact_identity_echo_valid": consumer_receipt_pass(
            row,
            "artifact_identity_echo_valid",
            "artifact_identity_echo_status",
        ),
        "value_consumed_by_decision": consumer_receipt_pass(
            row,
            "value_consumed_by_decision",
            "decision_consumption_status",
        ),
        "probe_evidence_ref": str(row.get("probe_evidence_ref") or ""),
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _collect_context_rows(values: tuple[Any, ...]) -> tuple[list[str], list[dict[str, Any]]]:
    required_ids: list[str] = []
    rows: list[dict[str, Any]] = []

    def collect(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                collect(child)
            return
        if not isinstance(value, dict):
            return
        for consumer_id in _values.list_values(value.get("required_consumer_ids")):
            text = str(consumer_id).strip()
            if text and text not in required_ids:
                required_ids.append(text)
        for key in ("consumer_context_conformance", "adapter_consumer_conformance"):
            nested = value.get(key)
            if isinstance(nested, dict):
                collect(nested)
            elif isinstance(nested, list):
                rows.extend(row for row in nested if isinstance(row, dict))
        nested_rows = value.get("rows")
        if isinstance(nested_rows, list):
            rows.extend(row for row in nested_rows if isinstance(row, dict))

    for value in values:
        collect(value)
    return required_ids, rows


def _exact_artifact_echo(
    candidate: dict[str, Any],
    expected: dict[str, Any],
    expected_cycle_id: str | None,
    expected_input_state_fingerprint: str | None,
    expected_attempt_identity: str | None,
) -> bool:
    body_fingerprint = str(
        expected.get("body_projection_fingerprint") or ""
    ).strip().lower()
    verification_ids = sorted(
        str(item) for item in _vectors.string_list(expected.get("verification_input_ids"))
    )
    cohort_present = bool(verification_ids) or isinstance(
        expected.get("input_fingerprints"), dict
    )
    if not expected or not re.fullmatch(r"[0-9a-f]{64}", body_fingerprint):
        return False
    if not cohort_present or not expected_cycle_id or not expected_input_state_fingerprint:
        return False
    if not expected_attempt_identity:
        return False
    if candidate.get("cycle_id") != expected_cycle_id:
        return False
    if candidate.get("input_state_fingerprint") != expected_input_state_fingerprint:
        return False
    if candidate.get("attempt_identity") != expected_attempt_identity:
        return False
    for field in ("artifact_id", "artifact_sha256", "production_lane_identity"):
        if not expected.get(field) or candidate.get(field) != expected.get(field):
            return False
    if expected.get("body_projection_fingerprint") and candidate.get(
        "body_projection_fingerprint"
    ) != expected.get("body_projection_fingerprint"):
        return False
    if expected.get("verification_input_ids") is not None and sorted(
        str(item)
        for item in _vectors.string_list(candidate.get("verification_input_ids"))
    ) != verification_ids:
        return False
    return not (
        expected.get("input_fingerprints") is not None
        and candidate.get("input_fingerprints") != expected.get("input_fingerprints")
    )


def _receipt_valid(
    candidate: dict[str, Any],
    expected: dict[str, Any],
    expected_cycle_id: str | None,
    expected_input_state_fingerprint: str | None,
    expected_attempt_identity: str | None,
) -> bool:
    required_flags = all(
        _values.bool_value(candidate.get(field))
        for field in (
            "adapter_loaded",
            "hook_resolved",
            "required_hook_callable",
            "hook_signature_compatible",
            "return_contract_valid",
        )
    )
    receipt_passes = all(
        (
            consumer_receipt_pass(candidate, "invocation_completed", "invocation_status"),
            consumer_receipt_pass(
                candidate, "artifact_identity_echo_valid", "artifact_identity_echo_status"
            ),
            consumer_receipt_pass(
                candidate, "value_consumed_by_decision", "decision_consumption_status"
            ),
        )
    )
    probe_sha = str(candidate.get("probe_evidence_sha256") or "").lower()
    return bool(
        candidate
        and required_flags
        and receipt_passes
        and str(candidate.get("evidence_provenance") or "").strip().lower()
        in {"independently_verified", "self_grounded"}
        and _exact_artifact_echo(
            candidate,
            expected,
            expected_cycle_id,
            expected_input_state_fingerprint,
            expected_attempt_identity,
        )
        and str(candidate.get("probe_evidence_ref") or "").strip()
        and re.fullmatch(r"[0-9a-f]{64}", probe_sha)
        and probe_sha == consumer_receipt_binding_sha256(candidate)
    )


def _normalized_receipt(
    consumer_id: str,
    row: dict[str, Any],
    source_receipt_count: int,
    valid: bool,
) -> dict[str, Any]:
    return {
        "consumer_context_id": str(consumer_id),
        "adapter_loaded": _values.bool_value(row.get("adapter_loaded")),
        "hook_resolved": _values.bool_value(
            row.get("hook_resolved")
            if "hook_resolved" in row
            else row.get("required_hook_callable")
        ),
        "required_hook_callable": _values.bool_value(row.get("required_hook_callable")),
        "hook_signature_compatible": _values.bool_value(row.get("hook_signature_compatible")),
        "invocation_completed": consumer_receipt_pass(
            row, "invocation_completed", "invocation_status"
        ),
        "return_contract_valid": _values.bool_value(row.get("return_contract_valid")),
        "artifact_identity_echo_valid": consumer_receipt_pass(
            row, "artifact_identity_echo_valid", "artifact_identity_echo_status"
        ),
        "cycle_id": row.get("cycle_id"),
        "input_state_fingerprint": row.get("input_state_fingerprint"),
        "attempt_identity": row.get("attempt_identity"),
        "artifact_id": row.get("artifact_id"),
        "artifact_sha256": row.get("artifact_sha256"),
        "production_lane_identity": row.get("production_lane_identity"),
        "body_projection_fingerprint": row.get("body_projection_fingerprint"),
        "verification_input_ids": _vectors.string_list(row.get("verification_input_ids")),
        "input_fingerprints": (
            row.get("input_fingerprints")
            if isinstance(row.get("input_fingerprints"), dict)
            else None
        ),
        "evidence_provenance": row.get("evidence_provenance"),
        "value_consumed_by_decision": consumer_receipt_pass(
            row, "value_consumed_by_decision", "decision_consumption_status"
        ),
        "probe_evidence_id": row.get("probe_evidence_id"),
        "probe_evidence_ref": row.get("probe_evidence_ref"),
        "probe_evidence_sha256": row.get("probe_evidence_sha256"),
        "source_receipt_count": source_receipt_count,
        "status": "pass" if valid else "not_evaluated",
    }


def consumer_context_conformance_gate(
    *values: Any,
    expected_artifact_ref: dict[str, Any] | None = None,
    expected_cycle_id: str | None = None,
    expected_input_state_fingerprint: str | None = None,
    expected_attempt_identity: str | None = None,
) -> dict[str, Any]:
    required_ids, rows = _collect_context_rows(values)
    by_id: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        consumer_id = str(row.get("consumer_context_id") or "").strip()
        if consumer_id:
            by_id.setdefault(consumer_id, []).append(row)
    missing: list[str] = []
    normalized: list[dict[str, Any]] = []
    consumer_ids = list(dict.fromkeys([*required_ids, *by_id.keys()]))
    for consumer_id in consumer_ids:
        candidate_rows = by_id.get(str(consumer_id)) or [{}]
        row = candidate_rows[-1]
        valid = all(
            _receipt_valid(
                candidate,
                expected_artifact_ref or {},
                expected_cycle_id,
                expected_input_state_fingerprint,
                expected_attempt_identity,
            )
            for candidate in candidate_rows
        )
        normalized.append(_normalized_receipt(consumer_id, row, len(candidate_rows), valid))
        if consumer_id in required_ids and not valid:
            missing.append(str(consumer_id))
    return {
        "required_consumer_ids": required_ids,
        "rows": normalized,
        "missing_consumer_context_ids": missing,
        "status": "pass" if required_ids and not missing else ("not_evaluated" if required_ids else "not_applicable"),
    }
