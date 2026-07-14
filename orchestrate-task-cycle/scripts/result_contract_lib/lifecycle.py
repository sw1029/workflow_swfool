from __future__ import annotations

from typing import Any

from .common import boolish, first_present
from .finalization import full_sha256, opaque_id


OPTION_CLASSES = {"blocker_removing", "non_removing_but_useful", "terminal_or_wait"}
OPTION_APPLICABILITY = {"applicable", "not_applicable", "not_evaluated"}
OPTION_INVENTORY_STATUSES = {"complete", "incomplete", "not_evaluated"}
OPERATIONS = (
    "read_diagnostic",
    "offline_transform",
    "publish",
    "promote_or_adopt",
    "destructive_disposition",
)
OPERATION_STATUSES = {"allowed", "blocked", "not_applicable", "unknown"}
STATE_CHANGING_OPERATIONS = set(OPERATIONS) - {"read_diagnostic"}


def _finding(severity: str, code: str, message: str, evidence: Any = None) -> dict[str, Any]:
    row: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if evidence is not None:
        row["evidence"] = evidence
    return row


def _opaque_list(value: Any) -> tuple[list[str], bool]:
    if not isinstance(value, list):
        return [], False
    normalized = [item for item in value if opaque_id(item)]
    return normalized, len(normalized) == len(value) and len(normalized) == len(set(normalized))


def validate_option_inventory(target: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = first_present(result, ["option_inventory", "escalation.option_inventory", "result.option_inventory"])
    required = boolish(first_present(result, ["option_inventory_required", "escalation_required", "result.option_inventory_required"]))
    if inventory is None:
        return [
            _finding(
                "block",
                "option_inventory_missing",
                "An applicable escalation decision requires a typed option inventory.",
            )
        ] if required else []
    if not isinstance(inventory, dict):
        return [_finding("block", "option_inventory_invalid", "Option inventory must be an object.")]

    findings: list[dict[str, Any]] = []
    if inventory.get("schema_version") != 1:
        findings.append(_finding("block", "option_inventory_schema_invalid", "Option inventory requires schema_version=1."))
    status = str(inventory.get("inventory_status") or "").strip().lower()
    if status not in OPTION_INVENTORY_STATUSES:
        findings.append(_finding("block", "option_inventory_status_invalid", "Option inventory status is invalid."))
    options = inventory.get("options")
    if not isinstance(options, list):
        findings.append(_finding("block", "option_inventory_options_invalid", "Option inventory requires an explicit options list, including []."))
        options = []
    seen_ids: set[str] = set()
    applicable_blocker_removing = False
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            findings.append(_finding("block", "option_inventory_row_invalid", "Option rows must be objects.", {"index": index}))
            continue
        option_id = option.get("option_id")
        option_class = str(option.get("option_class") or "").strip().lower()
        applicability = str(option.get("applicability") or "").strip().lower()
        evidence_ids, evidence_valid = _opaque_list(option.get("evidence_ids"))
        if not opaque_id(option_id) or option_id in seen_ids:
            findings.append(_finding("block", "option_inventory_id_invalid", "Option IDs must be unique bounded opaque strings.", {"index": index}))
        else:
            seen_ids.add(option_id)
        if option_class not in OPTION_CLASSES:
            findings.append(_finding("block", "option_inventory_class_invalid", "Option class is outside the closed vocabulary.", {"index": index}))
        if applicability not in OPTION_APPLICABILITY:
            findings.append(_finding("block", "option_inventory_applicability_invalid", "Option applicability is outside the closed vocabulary.", {"index": index}))
        if not evidence_valid or not evidence_ids:
            findings.append(_finding("block", "option_inventory_evidence_invalid", "Each option requires bounded evidence IDs for authority and producer applicability.", {"index": index}))
        if option_class == "blocker_removing" and applicability == "applicable":
            applicable_blocker_removing = True

    declared_present = inventory.get("blocker_removing_option_present")
    if not isinstance(declared_present, bool) or declared_present != applicable_blocker_removing:
        findings.append(
            _finding(
                "block",
                "blocker_removing_option_presence_mismatch",
                "Blocker-removing option presence must be derived from applicable inventory rows.",
            )
        )
    incomplete = inventory.get("options_incomplete")
    expected_incomplete = status != "complete"
    if not isinstance(incomplete, bool) or incomplete != expected_incomplete:
        findings.append(_finding("block", "option_inventory_completeness_mismatch", "options_incomplete must match the typed inventory status."))
    if status == "complete" and not applicable_blocker_removing:
        reason = inventory.get("blocker_removing_absence_reason")
        evidence_ids, evidence_valid = _opaque_list(inventory.get("blocker_removing_absence_evidence_ids"))
        if not opaque_id(reason) or not evidence_valid or not evidence_ids:
            findings.append(
                _finding(
                    "block",
                    "blocker_removing_absence_unproven",
                    "A complete inventory with no applicable blocker-removing option requires an evidence-bound absence reason.",
                )
            )
    terminal_or_authority_claim = bool(
        boolish(first_present(result, ["hard_stop", "hard_stop_required", "terminal_state", "terminal_blocker"]))
        or str(first_present(result, ["completion_status", "selected_task_source", "selected_disposition"]) or "").strip().lower()
        in {"complete", "complete_verified", "final_goal_complete", "terminal", "terminal_blocked"}
        or boolish(first_present(result, ["authority_expansion_granted", "authority_conclusion_final"]))
    )
    if status != "complete" and terminal_or_authority_claim:
        findings.append(
            _finding(
                "block",
                "incomplete_options_control_terminal_or_authority",
                "An incomplete option inventory may request information but cannot establish terminal, completion, or authority truth.",
            )
        )
    return findings


def validate_gate_operation_applicability(target: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    matrix = first_present(
        result,
        [
            "gate_operation_applicability",
            "gate_compatibility.operation_applicability",
            "result.gate_operation_applicability",
        ],
    )
    required = boolish(
        first_present(
            result,
            [
                "gate_operation_applicability_required",
                "state_changing_gate_consumption",
                "result.gate_operation_applicability_required",
            ],
        )
    )
    requested = str(
        first_present(result, ["requested_operation", "decision_operation", "operation", "result.requested_operation"])
        or ""
    ).strip().lower()
    consumed = boolish(first_present(result, ["operation_consumed", "decision_operation_consumed", "state_changing_gate_consumption"]))
    if matrix is None:
        return [
            _finding(
                "block",
                "gate_operation_applicability_missing",
                "State-changing gate consumption requires adapter/authority-supplied operation applicability.",
            )
        ] if required or consumed else []
    if not isinstance(matrix, dict):
        return [_finding("block", "gate_operation_applicability_invalid", "Gate operation applicability must be an object.")]

    findings: list[dict[str, Any]] = []
    if matrix.get("schema_version") != 1:
        findings.append(_finding("block", "gate_operation_applicability_schema_invalid", "Operation applicability requires schema_version=1."))
    matrix_status = str(matrix.get("matrix_status") or "").strip().lower()
    if matrix_status not in {"complete", "incomplete", "not_evaluated"}:
        findings.append(_finding("block", "gate_operation_matrix_status_invalid", "Operation applicability matrix status is invalid."))
    operations = matrix.get("operations")
    if not isinstance(operations, dict):
        findings.append(_finding("block", "gate_operation_rows_invalid", "Operation applicability requires an operations object."))
        operations = {}
    unknown_names = sorted(set(operations) - set(OPERATIONS))
    if unknown_names:
        findings.append(_finding("block", "gate_operation_name_invalid", "Operation applicability contains unknown operation names.", {"operations": unknown_names}))
    if matrix_status == "complete" and set(operations) != set(OPERATIONS):
        findings.append(
            _finding(
                "block",
                "gate_operation_matrix_incomplete",
                "A complete matrix must classify every operation in the closed vocabulary.",
                {"missing": sorted(set(OPERATIONS) - set(operations))},
            )
        )
    normalized: dict[str, str] = {}
    for operation in OPERATIONS:
        row = operations.get(operation)
        if row is None:
            continue
        if not isinstance(row, dict):
            findings.append(_finding("block", "gate_operation_row_invalid", "Operation applicability rows must be objects.", {"operation": operation}))
            continue
        status = str(row.get("status") or "").strip().lower()
        normalized[operation] = status
        evidence_ids, evidence_valid = _opaque_list(row.get("evidence_ids"))
        if status not in OPERATION_STATUSES:
            findings.append(_finding("block", "gate_operation_status_invalid", "Operation applicability status is invalid.", {"operation": operation}))
        if status in {"allowed", "blocked", "not_applicable"} and (not evidence_valid or not evidence_ids):
            findings.append(_finding("block", "gate_operation_evidence_invalid", "Evaluated operation applicability requires bounded evidence IDs.", {"operation": operation}))
    if requested and requested not in OPERATIONS:
        findings.append(_finding("block", "requested_operation_invalid", "Requested operation is outside the closed vocabulary."))
        return findings
    if requested:
        status = normalized.get(requested, "unknown")
        if consumed and (status != "allowed" or matrix_status != "complete"):
            findings.append(
                _finding(
                    "block",
                    "gate_operation_not_allowed_for_consumption",
                    "Unknown, blocked, non-applicable, or incomplete operation scope cannot authorize consumption.",
                    {"operation": requested, "status": status, "matrix_status": matrix_status},
                )
            )
        if requested in STATE_CHANGING_OPERATIONS and status == "unknown":
            findings.append(_finding("block", "state_changing_operation_scope_unknown", "State-changing operation scope must fail closed when applicability is unknown.", {"operation": requested}))
        if requested == "read_diagnostic" and status == "allowed" and consumed:
            read_contract = matrix.get("read_contract")
            valid_read_contract = bool(
                isinstance(read_contract, dict)
                and read_contract.get("authority_status") == "verified"
                and read_contract.get("safety_status") == "verified"
                and read_contract.get("privacy_status") == "verified"
                and read_contract.get("provenance_status") == "verified"
                and opaque_id(read_contract.get("receipt_ref"), max_length=512)
                and full_sha256(read_contract.get("receipt_hash"))
            )
            if not valid_read_contract:
                findings.append(
                    _finding(
                        "block",
                        "read_diagnostic_contract_unverified",
                        "Operation applicability alone does not grant read authority; verified authority, safety, privacy, and provenance are required.",
                    )
                )
    return findings


def validate_lifecycle_extensions(target: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    return validate_option_inventory(target, result) + validate_gate_operation_applicability(target, result)
