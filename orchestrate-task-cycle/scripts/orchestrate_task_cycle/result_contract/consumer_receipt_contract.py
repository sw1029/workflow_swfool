from __future__ import annotations

import hashlib
import json
from typing import Any

from .common import boolish, list_values


COVERAGE_FIELDS = (
    "required_hook_ids",
    "required_gate_ids",
    "consumed_hook_ids",
    "consumed_gate_ids",
    "excluded_gate_ids",
)
HOOK_IO_FIELDS = {
    "acceptance_required",
    "hook_id",
    "input_sha256",
    "invocation_index",
    "output_sha256",
    "return_contract_valid",
    "semantic_status",
    "signature_sha256",
    "status",
    "value_consumed_by_decision",
}
CONSUMER_RECEIPT_CONTRACT_VERSION = 2


def _static_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


VALIDATOR_SIGNATURE_SHA256 = _static_sha256(
    {
        "contract_version": CONSUMER_RECEIPT_CONTRACT_VERSION,
        "coverage_fields": COVERAGE_FIELDS,
        "hook_io_fields": sorted(HOOK_IO_FIELDS),
        "semantic_statuses": ["accepted", "not_evaluated"],
        "statuses": ["completed", "failed", "unavailable"],
    }
)
CONSUMER_REVISION_SHA256 = _static_sha256(
    {"consumer_id": "audit-cycle-loopback", "validator": VALIDATOR_SIGNATURE_SHA256}
)


def _full_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _declared_id_list(row: dict[str, Any], field: str) -> tuple[list[str], bool]:
    if field not in row or not isinstance(row.get(field), list):
        return [], False
    values = row[field]
    normalized = [
        item.strip() for item in values if isinstance(item, str) and item.strip()
    ]
    return normalized, len(normalized) == len(values) and len(set(normalized)) == len(
        normalized
    )


def _expected_id_list(value: Any) -> tuple[list[str] | None, bool]:
    if value is None:
        return None, True
    if not isinstance(value, (list, tuple, set)):
        return [], False
    normalized = [
        item.strip() for item in value if isinstance(item, str) and item.strip()
    ]
    return sorted(normalized), len(normalized) == len(value) and len(
        set(normalized)
    ) == len(normalized)


def _hash_id_list(row: dict[str, Any], field: str) -> Any:
    if field not in row:
        return {"declaration": "missing"}
    value = row.get(field)
    if not isinstance(value, list):
        return {"declaration": "invalid_type", "type": type(value).__name__}
    return sorted(str(item) for item in value)


def consumer_receipt_coverage_declared(row: dict[str, Any]) -> bool:
    return any(field in row for field in COVERAGE_FIELDS)


def _local_coverage_status(row: dict[str, Any]) -> str:
    if not consumer_receipt_coverage_declared(row):
        return "legacy"
    parsed = {field: _declared_id_list(row, field) for field in COVERAGE_FIELDS}
    if not all(valid for _, valid in parsed.values()):
        return "not_evaluated"
    required_hooks = set(parsed["required_hook_ids"][0])
    required_gates = set(parsed["required_gate_ids"][0])
    consumed_hooks = set(parsed["consumed_hook_ids"][0])
    consumed_gates = set(parsed["consumed_gate_ids"][0])
    excluded_gates = set(parsed["excluded_gate_ids"][0])
    if consumed_hooks != required_hooks:
        return "not_evaluated"
    if consumed_gates & excluded_gates:
        return "not_evaluated"
    if consumed_gates | excluded_gates != required_gates:
        return "not_evaluated"
    return "not_evaluated" if excluded_gates else "conformant"


def validate_consumer_receipt_binding(
    row: dict[str, Any],
    *,
    expected_task_id: str | None = None,
    expected_adapter_revision_sha256: str | None = None,
    expected_hook_id: str | None = None,
    expected_consumer_revision_sha256: str | None = None,
    expected_required_hook_ids: Any = None,
    expected_required_gate_ids: Any = None,
) -> dict[str, Any]:
    """Validate current identity and exact explicit hook/gate coverage."""
    mismatches: list[str] = []
    expected_hooks, hooks_valid = _expected_id_list(expected_required_hook_ids)
    expected_gates, gates_valid = _expected_id_list(expected_required_gate_ids)
    explicit = bool(
        expected_hooks is not None
        or expected_gates is not None
        or consumer_receipt_coverage_declared(row)
    )
    if expected_task_id and row.get("task_id") != expected_task_id:
        mismatches.append("task_id")
    if (
        expected_adapter_revision_sha256
        and row.get("adapter_revision_sha256") != expected_adapter_revision_sha256
    ):
        mismatches.append("adapter_revision_sha256")
    inferred_hook_id = expected_hook_id
    if (
        inferred_hook_id is None
        and expected_hooks is not None
        and len(expected_hooks) == 1
    ):
        inferred_hook_id = expected_hooks[0]
    if inferred_hook_id and row.get("hook_id") != inferred_hook_id:
        mismatches.append("hook_id")
    if not explicit:
        return {
            "explicit": False,
            "status": "legacy",
            "mismatched_fields": sorted(set(mismatches)),
            "excluded_required_gate_ids": [],
        }
    if row.get("consumer_contract_version") != CONSUMER_RECEIPT_CONTRACT_VERSION:
        mismatches.append("consumer_contract_version")
    if not _full_sha256(row.get("consumer_revision_sha256")):
        mismatches.append("consumer_revision_sha256")
    elif (
        expected_consumer_revision_sha256
        and row.get("consumer_revision_sha256") != expected_consumer_revision_sha256
    ):
        mismatches.append("consumer_revision_sha256")
    if row.get("validator_signature_sha256") != VALIDATOR_SIGNATURE_SHA256:
        mismatches.append("validator_signature_sha256")
    if not hooks_valid:
        mismatches.append("expected_required_hook_ids")
    if not gates_valid:
        mismatches.append("expected_required_gate_ids")
    parsed = {field: _declared_id_list(row, field) for field in COVERAGE_FIELDS}
    for field, (_, valid) in parsed.items():
        if not valid:
            mismatches.append(field)
    required_hooks = set(parsed["required_hook_ids"][0])
    required_gates = set(parsed["required_gate_ids"][0])
    consumed_hooks = set(parsed["consumed_hook_ids"][0])
    consumed_gates = set(parsed["consumed_gate_ids"][0])
    excluded_gates = set(parsed["excluded_gate_ids"][0])
    hook_io = row.get("hook_io_receipts")
    valid_hook_io = isinstance(hook_io, list) and bool(hook_io)
    consumed_io_hooks: set[str] = set()
    if valid_hook_io:
        indices: list[int] = []
        for invocation in hook_io:
            if not isinstance(invocation, dict) or set(invocation) != HOOK_IO_FIELDS:
                valid_hook_io = False
                continue
            indices.append(invocation.get("invocation_index"))
            if (
                not isinstance(invocation.get("invocation_index"), int)
                or invocation.get("invocation_index") < 0
                or not all(
                    _full_sha256(invocation.get(field))
                    for field in ("input_sha256", "output_sha256", "signature_sha256")
                )
                or not isinstance(invocation.get("hook_id"), str)
                or not invocation.get("hook_id", "").strip()
                or invocation.get("status")
                not in {"completed", "failed", "unavailable"}
                or not isinstance(invocation.get("return_contract_valid"), bool)
                or not isinstance(invocation.get("acceptance_required"), bool)
                or invocation.get("semantic_status")
                not in {"accepted", "not_evaluated"}
                or not isinstance(invocation.get("value_consumed_by_decision"), bool)
            ):
                valid_hook_io = False
            elif (
                invocation["status"] == "completed"
                and invocation["return_contract_valid"] is True
                and invocation["semantic_status"] == "accepted"
                and invocation["value_consumed_by_decision"] is True
            ):
                consumed_io_hooks.add(invocation["hook_id"])
        if len(indices) != len(set(indices)):
            valid_hook_io = False
    if not valid_hook_io:
        mismatches.append("hook_io_receipts")
    elif consumed_io_hooks & required_hooks != consumed_hooks:
        mismatches.append("hook_io_consumption")
    if expected_hooks is None:
        mismatches.append("required_hook_ids_unbound")
    elif required_hooks != set(expected_hooks):
        mismatches.append("required_hook_ids")
    if (
        inferred_hook_id
        and expected_hooks is not None
        and inferred_hook_id not in expected_hooks
    ):
        mismatches.append("hook_id_not_required")
    if expected_gates is None:
        mismatches.append("required_gate_ids_unbound")
    elif required_gates != set(expected_gates):
        mismatches.append("required_gate_ids")
    if consumed_hooks != required_hooks:
        mismatches.append("consumed_hook_ids")
    if consumed_gates & excluded_gates:
        mismatches.append("gate_coverage_overlap")
    if consumed_gates | excluded_gates != required_gates:
        mismatches.append("gate_coverage")
    excluded_required = sorted(excluded_gates & required_gates)
    status = "not_evaluated" if mismatches or excluded_required else "conformant"
    declared_status = str(row.get("result_contract_status") or "").strip().lower()
    if declared_status != status:
        mismatches.append("result_contract_status")
        status = "not_evaluated"
    return {
        "explicit": True,
        "status": status,
        "mismatched_fields": sorted(set(mismatches)),
        "excluded_required_gate_ids": excluded_required,
    }


def _pass_value(row: dict[str, Any], bool_field: str, status_field: str) -> bool:
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


def consumer_receipt_binding_basis(row: dict[str, Any]) -> dict[str, Any]:
    """Return the one canonical cross-owner consumer-receipt hash basis."""
    basis: dict[str, Any] = {
        "consumer_context_id": str(row.get("consumer_context_id") or ""),
        "hook_id": str(row.get("hook_id") or ""),
        "cycle_id": str(row.get("cycle_id") or ""),
        "task_id": str(row.get("task_id") or ""),
        "input_state_fingerprint": str(row.get("input_state_fingerprint") or ""),
        "attempt_identity": str(row.get("attempt_identity") or ""),
        "adapter_revision_sha256": str(row.get("adapter_revision_sha256") or ""),
        "consumer_contract_version": row.get("consumer_contract_version"),
        "consumer_revision_sha256": row.get("consumer_revision_sha256"),
        "validator_signature_sha256": row.get("validator_signature_sha256"),
        "hook_io_receipts": row.get("hook_io_receipts"),
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
        "evidence_provenance": str(row.get("evidence_provenance") or "")
        .strip()
        .lower(),
        "adapter_loaded": boolish(row.get("adapter_loaded")),
        "hook_resolved": boolish(
            row.get("hook_resolved")
            if "hook_resolved" in row
            else row.get("required_hook_callable")
        ),
        "required_hook_callable": boolish(row.get("required_hook_callable")),
        "hook_signature_compatible": boolish(row.get("hook_signature_compatible")),
        "invocation_completed": _pass_value(
            row, "invocation_completed", "invocation_status"
        ),
        "return_contract_valid": boolish(row.get("return_contract_valid")),
        "artifact_identity_echo_valid": _pass_value(
            row, "artifact_identity_echo_valid", "artifact_identity_echo_status"
        ),
        "value_consumed_by_decision": _pass_value(
            row, "value_consumed_by_decision", "decision_consumption_status"
        ),
        "probe_evidence_ref": str(row.get("probe_evidence_ref") or ""),
    }
    if row.get("decision_identity_echo") is not None:
        basis["decision_identity_echo"] = row.get("decision_identity_echo")
    if consumer_receipt_coverage_declared(row):
        basis["coverage"] = {
            field: _hash_id_list(row, field) for field in COVERAGE_FIELDS
        }
        basis["coverage_evaluation_status"] = _local_coverage_status(row)
        if "result_contract_status" in row:
            basis["result_contract_status"] = (
                str(row.get("result_contract_status") or "").strip().lower()
            )
    return basis


def consumer_receipt_binding_sha256(row: dict[str, Any]) -> str:
    raw = json.dumps(
        consumer_receipt_binding_basis(row),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "COVERAGE_FIELDS",
    "CONSUMER_RECEIPT_CONTRACT_VERSION",
    "CONSUMER_REVISION_SHA256",
    "HOOK_IO_FIELDS",
    "VALIDATOR_SIGNATURE_SHA256",
    "consumer_receipt_binding_basis",
    "consumer_receipt_binding_sha256",
    "consumer_receipt_coverage_declared",
    "validate_consumer_receipt_binding",
]
