from __future__ import annotations

import re
from typing import Any

from .consumer_receipt_contract import (
    consumer_receipt_binding_sha256,
    validate_consumer_receipt_binding,
)
from .decision_identity_dimensions import (
    parse_decision_identity,
)

from . import values as _values
from . import vectors as _vectors
from .decision_identity_binding import (
    decision_identity_echo,
    explicit_identity,
    explicit_identity_mismatches,
)


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


def _contract_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if not isinstance(value, dict):
        return []
    if value.get("consumer_id") or value.get("consumer_context_id"):
        return [value]
    return [
        {"consumer_id": consumer_id, **row}
        for consumer_id, row in value.items()
        if isinstance(row, dict)
    ]


def _collect_context_rows(
    values: tuple[Any, ...],
) -> tuple[list[str], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    required_ids: list[str] = []
    rows: list[dict[str, Any]] = []
    contracts: dict[str, list[dict[str, Any]]] = {}

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
        for key in ("consumer_contract", "consumer_contracts"):
            for row in _contract_rows(value.get(key)):
                consumer_id = str(
                    row.get("consumer_id") or row.get("consumer_context_id") or ""
                ).strip()
                if consumer_id:
                    contracts.setdefault(consumer_id, []).append(row)
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
    return required_ids, rows, contracts


def _consumer_expectation(
    consumer_id: str,
    contracts: dict[str, list[dict[str, Any]]],
    defaults: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    expectation = dict(defaults)
    conflicted = False
    field_names = (
        "task_id",
        "adapter_revision_sha256",
        "consumer_revision_sha256",
        "hook_id",
        "required_hook_ids",
        "required_gate_ids",
    )
    for contract in contracts.get(consumer_id, []):
        for field in field_names:
            if field not in contract:
                continue
            current = expectation.get(field)
            supplied = contract[field]
            equal = current == supplied
            if (
                field in {"required_hook_ids", "required_gate_ids"}
                and isinstance(current, list)
                and isinstance(supplied, list)
            ):
                equal = sorted(current) == sorted(supplied)
            if current is not None and not equal:
                conflicted = True
            else:
                expectation[field] = supplied
    explicit_sets = any(
        expectation.get(field) is not None
        for field in ("required_hook_ids", "required_gate_ids")
    )
    if explicit_sets:
        for field in ("required_hook_ids", "required_gate_ids"):
            if expectation.get(field) is None:
                expectation[field] = []
    return expectation, conflicted


def _exact_artifact_echo(
    candidate: dict[str, Any],
    expected: dict[str, Any],
    expected_cycle_id: str | None,
    expected_input_state_fingerprint: str | None,
    expected_attempt_identity: str | None,
    expected_task_id: str | None,
    expected_adapter_revision_sha256: str | None,
) -> bool:
    if not expected:
        return False
    exact_identity = explicit_identity(expected)
    projection = parse_decision_identity(exact_identity or expected)
    if projection.explicit:
        if explicit_identity_mismatches(candidate, expected):
            return False
    else:
        body_fingerprint = (
            str(expected.get("body_projection_fingerprint") or "").strip().lower()
        )
        verification_ids = sorted(
            str(item)
            for item in _vectors.string_list(expected.get("verification_input_ids"))
        )
        cohort_present = bool(verification_ids) or isinstance(
            expected.get("input_fingerprints"), dict
        )
        if not re.fullmatch(r"[0-9a-f]{64}", body_fingerprint):
            return False
        if not cohort_present:
            return False
        for field in ("artifact_id", "artifact_sha256", "production_lane_identity"):
            if not expected.get(field) or candidate.get(field) != expected.get(field):
                return False
        if expected.get("body_projection_fingerprint") and candidate.get(
            "body_projection_fingerprint"
        ) != expected.get("body_projection_fingerprint"):
            return False
        if (
            expected.get("verification_input_ids") is not None
            and sorted(
                str(item)
                for item in _vectors.string_list(candidate.get("verification_input_ids"))
            )
            != verification_ids
        ):
            return False
        if (
            expected.get("input_fingerprints") is not None
            and candidate.get("input_fingerprints")
            != expected.get("input_fingerprints")
        ):
            return False
    if not expected_cycle_id or not expected_input_state_fingerprint:
        return False
    if not expected_attempt_identity:
        return False
    if expected_task_id and candidate.get("task_id") != expected_task_id:
        return False
    if (
        expected_adapter_revision_sha256
        and candidate.get("adapter_revision_sha256") != expected_adapter_revision_sha256
    ):
        return False
    if candidate.get("cycle_id") != expected_cycle_id:
        return False
    if candidate.get("input_state_fingerprint") != expected_input_state_fingerprint:
        return False
    if candidate.get("attempt_identity") != expected_attempt_identity:
        return False
    return True


def _receipt_valid(
    candidate: dict[str, Any],
    expected: dict[str, Any],
    expected_cycle_id: str | None,
    expected_input_state_fingerprint: str | None,
    expected_attempt_identity: str | None,
    expected_task_id: str | None,
    expected_adapter_revision_sha256: str | None,
    expected_consumer_revision_sha256: str | None,
    expected_hook_id: str | None,
    expected_required_hook_ids: Any,
    expected_required_gate_ids: Any,
    expectation_conflicted: bool,
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
            consumer_receipt_pass(
                candidate, "invocation_completed", "invocation_status"
            ),
            consumer_receipt_pass(
                candidate,
                "artifact_identity_echo_valid",
                "artifact_identity_echo_status",
            ),
            consumer_receipt_pass(
                candidate, "value_consumed_by_decision", "decision_consumption_status"
            ),
        )
    )
    probe_sha = str(candidate.get("probe_evidence_sha256") or "").lower()
    binding = validate_consumer_receipt_binding(
        candidate,
        expected_task_id=expected_task_id,
        expected_adapter_revision_sha256=expected_adapter_revision_sha256,
        expected_hook_id=expected_hook_id,
        expected_consumer_revision_sha256=expected_consumer_revision_sha256,
        expected_required_hook_ids=expected_required_hook_ids,
        expected_required_gate_ids=expected_required_gate_ids,
    )
    return bool(
        candidate
        and not expectation_conflicted
        and not binding["mismatched_fields"]
        and binding["status"] in {"legacy", "conformant"}
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
            expected_task_id,
            expected_adapter_revision_sha256,
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
    binding: dict[str, Any],
) -> dict[str, Any]:
    identity_echo = decision_identity_echo(row)
    normalized = {
        "consumer_context_id": str(consumer_id),
        "hook_id": row.get("hook_id"),
        "adapter_loaded": _values.bool_value(row.get("adapter_loaded")),
        "hook_resolved": _values.bool_value(
            row.get("hook_resolved")
            if "hook_resolved" in row
            else row.get("required_hook_callable")
        ),
        "required_hook_callable": _values.bool_value(row.get("required_hook_callable")),
        "hook_signature_compatible": _values.bool_value(
            row.get("hook_signature_compatible")
        ),
        "invocation_completed": consumer_receipt_pass(
            row, "invocation_completed", "invocation_status"
        ),
        "return_contract_valid": _values.bool_value(row.get("return_contract_valid")),
        "artifact_identity_echo_valid": consumer_receipt_pass(
            row, "artifact_identity_echo_valid", "artifact_identity_echo_status"
        ),
        "cycle_id": row.get("cycle_id"),
        "task_id": row.get("task_id"),
        "input_state_fingerprint": row.get("input_state_fingerprint"),
        "attempt_identity": row.get("attempt_identity"),
        "adapter_revision_sha256": row.get("adapter_revision_sha256"),
        "consumer_contract_version": row.get("consumer_contract_version"),
        "consumer_revision_sha256": row.get("consumer_revision_sha256"),
        "validator_signature_sha256": row.get("validator_signature_sha256"),
        "hook_io_receipts": row.get("hook_io_receipts"),
        "artifact_id": row.get("artifact_id"),
        "artifact_sha256": row.get("artifact_sha256"),
        "production_lane_identity": row.get("production_lane_identity"),
        "body_projection_fingerprint": row.get("body_projection_fingerprint"),
        "verification_input_ids": _vectors.string_list(
            row.get("verification_input_ids")
        ),
        "input_fingerprints": (
            row.get("input_fingerprints")
            if isinstance(row.get("input_fingerprints"), dict)
            else None
        ),
        "decision_identity_kind": "explicit_v2" if identity_echo else "legacy_v1",
        "decision_identity_echo": identity_echo,
        "evidence_provenance": row.get("evidence_provenance"),
        "value_consumed_by_decision": consumer_receipt_pass(
            row, "value_consumed_by_decision", "decision_consumption_status"
        ),
        "probe_evidence_id": row.get("probe_evidence_id"),
        "probe_evidence_ref": row.get("probe_evidence_ref"),
        "probe_evidence_sha256": row.get("probe_evidence_sha256"),
        "source_receipt_count": source_receipt_count,
        "coverage_status": binding["status"],
        "coverage_mismatched_fields": binding["mismatched_fields"],
        "excluded_required_gate_ids": binding["excluded_required_gate_ids"],
        "status": "pass" if valid else "not_evaluated",
    }
    if binding["explicit"]:
        normalized.update(
            {
                "required_hook_ids": _vectors.string_list(row.get("required_hook_ids")),
                "required_gate_ids": _vectors.string_list(row.get("required_gate_ids")),
                "consumed_hook_ids": _vectors.string_list(row.get("consumed_hook_ids")),
                "consumed_gate_ids": _vectors.string_list(row.get("consumed_gate_ids")),
                "excluded_gate_ids": _vectors.string_list(row.get("excluded_gate_ids")),
                "result_contract_status": row.get("result_contract_status"),
            }
        )
    return normalized


def consumer_context_conformance_gate(
    *values: Any,
    expected_artifact_ref: dict[str, Any] | None = None,
    expected_cycle_id: str | None = None,
    expected_input_state_fingerprint: str | None = None,
    expected_attempt_identity: str | None = None,
    expected_task_id: str | None = None,
    expected_adapter_revision_sha256: str | None = None,
    expected_consumer_revision_sha256: str | None = None,
    expected_hook_id: str | None = None,
    expected_required_hook_ids: list[str] | None = None,
    expected_required_gate_ids: list[str] | None = None,
) -> dict[str, Any]:
    required_ids, rows, contracts = _collect_context_rows(values)
    by_id: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        consumer_id = str(row.get("consumer_context_id") or "").strip()
        if consumer_id:
            by_id.setdefault(consumer_id, []).append(row)
    missing: list[str] = []
    normalized: list[dict[str, Any]] = []
    consumer_ids = list(dict.fromkeys([*required_ids, *by_id.keys()]))
    normalized_contracts: list[dict[str, Any]] = []
    for consumer_id in consumer_ids:
        candidate_rows = by_id.get(str(consumer_id)) or [{}]
        row = candidate_rows[-1]
        expectation, expectation_conflicted = _consumer_expectation(
            consumer_id,
            contracts,
            {
                "task_id": expected_task_id,
                "adapter_revision_sha256": expected_adapter_revision_sha256,
                "consumer_revision_sha256": expected_consumer_revision_sha256,
                "hook_id": expected_hook_id,
                "required_hook_ids": expected_required_hook_ids,
                "required_gate_ids": expected_required_gate_ids,
            },
        )
        valid = all(
            _receipt_valid(
                candidate,
                expected_artifact_ref or {},
                expected_cycle_id,
                expected_input_state_fingerprint,
                expected_attempt_identity,
                expectation.get("task_id"),
                expectation.get("adapter_revision_sha256"),
                expectation.get("consumer_revision_sha256"),
                expectation.get("hook_id"),
                expectation.get("required_hook_ids"),
                expectation.get("required_gate_ids"),
                expectation_conflicted,
            )
            for candidate in candidate_rows
        )
        binding = validate_consumer_receipt_binding(
            row,
            expected_task_id=expectation.get("task_id"),
            expected_adapter_revision_sha256=expectation.get("adapter_revision_sha256"),
            expected_hook_id=expectation.get("hook_id"),
            expected_consumer_revision_sha256=expectation.get(
                "consumer_revision_sha256"
            ),
            expected_required_hook_ids=expectation.get("required_hook_ids"),
            expected_required_gate_ids=expectation.get("required_gate_ids"),
        )
        normalized.append(
            _normalized_receipt(consumer_id, row, len(candidate_rows), valid, binding)
        )
        if any(
            expectation.get(field) is not None
            for field in ("required_hook_ids", "required_gate_ids")
        ):
            normalized_contracts.append(
                {
                    "consumer_id": consumer_id,
                    **{
                        key: value
                        for key, value in expectation.items()
                        if value is not None
                    },
                    "contract_conflicted": expectation_conflicted,
                }
            )
        if consumer_id in required_ids and not valid:
            missing.append(str(consumer_id))
    return {
        "required_consumer_ids": required_ids,
        "consumer_contracts": normalized_contracts,
        "rows": normalized,
        "missing_consumer_context_ids": missing,
        "status": "pass"
        if required_ids and not missing
        else ("not_evaluated" if required_ids else "not_applicable"),
    }
