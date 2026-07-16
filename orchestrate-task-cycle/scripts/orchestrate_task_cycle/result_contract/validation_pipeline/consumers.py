from __future__ import annotations

from typing import Any

from .shared import (
    _consumer_receipt_binding_sha256,
    _declared_values,
    _full_sha256,
    _positive_decision_claim,
    add,
    boolish,
    first_present,
    list_values,
    non_empty,
)
from .state import ValidationState


def _check_consumers_part_01(state: ValidationState) -> None:
    findings = state.findings
    mode = state.mode
    result = state.result
    target = state.target
    required_consumer_ids: list[Any] = []
    for declared_ids in _declared_values(
        result,
        (
            "required_consumer_ids",
            "adapter_contract.required_consumer_ids",
            "consumer_context_conformance.required_consumer_ids",
            "adapter_consumer_conformance.required_consumer_ids",
            "result.required_consumer_ids",
            "result.consumer_context_conformance.required_consumer_ids",
            "result.adapter_consumer_conformance.required_consumer_ids",
        ),
    ):
        for consumer_id in list_values(declared_ids):
            if consumer_id not in required_consumer_ids:
                required_consumer_ids.append(consumer_id)
    conformance_rows: list[Any] = []
    malformed_conformance_aliases: list[str] = []
    for conformance_path in (
        "consumer_context_conformance",
        "adapter_consumer_conformance",
        "result.consumer_context_conformance",
        "result.adapter_consumer_conformance",
    ):
        declared_surfaces = _declared_values(result, (conformance_path,))
        if not declared_surfaces:
            continue
        conformance_surface = declared_surfaces[0]
        rows_value = (
            conformance_surface.get("rows")
            if isinstance(conformance_surface, dict)
            else conformance_surface
        )
        if isinstance(rows_value, list):
            conformance_rows.extend(rows_value)
        elif not (isinstance(conformance_surface, dict) and "rows" not in conformance_surface):
            malformed_conformance_aliases.append(conformance_path)
    if malformed_conformance_aliases:
        add(
            findings,
            (
                "block"
                if mode == "block"
                or target == "validate"
                or _positive_decision_claim(target, result)
                else "warn"
            ),
            "consumer_context_conformance_alias_malformed",
            "Every declared consumer-conformance alias must contain a row list; malformed duplicates cannot be ignored in favor of a valid surface.",
            {"aliases": malformed_conformance_aliases},
        )
    conformance_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in conformance_rows:
        if isinstance(row, dict) and row.get("consumer_context_id"):
            conformance_by_id.setdefault(str(row["consumer_context_id"]), []).append(row)
    state.conformance_by_id = conformance_by_id
    state.required_consumer_ids = required_consumer_ids


def _check_consumers_part_02(state: ValidationState) -> None:
    result = state.result
    decision_identity = first_present(
        result,
        [
            "decision_input_identity",
            "decision_artifact_ref",
            "selected_artifact_ref",
            "artifact_ref",
            "actual_artifact_ref",
            "result.decision_input_identity",
        ],
    )
    decision_identity = decision_identity if isinstance(decision_identity, dict) else {}
    body_fingerprint_values = []
    if "body_projection_fingerprint" in decision_identity:
        body_fingerprint_values.append(decision_identity.get("body_projection_fingerprint"))
    body_fingerprint_values.extend(
        _declared_values(
            result,
            (
                "body_projection_fingerprint",
                "actual_artifact_truth.body_projection_fingerprint",
                "quality_review.body_projection_fingerprint",
                "result.body_projection_fingerprint",
            ),
        )
    )
    expected_body_fingerprint = next(
        (value for value in body_fingerprint_values if non_empty(value)),
        None,
    )
    verification_input_values = []
    if "verification_input_ids" in decision_identity:
        verification_input_values.append(decision_identity.get("verification_input_ids"))
    verification_input_values.extend(
        _declared_values(
            result,
            (
                "verification_input_ids",
                "verification_source_separation_gate.verification_input_ids",
                "result.verification_input_ids",
            ),
        )
    )
    expected_verification_input_ids = verification_input_values[0] if verification_input_values else None
    input_fingerprint_values = []
    if "input_fingerprints" in decision_identity:
        input_fingerprint_values.append(decision_identity.get("input_fingerprints"))
    state.decision_identity = decision_identity
    state.expected_body_fingerprint = expected_body_fingerprint
    state.expected_verification_input_ids = expected_verification_input_ids
    state.input_fingerprint_values = input_fingerprint_values


def _check_consumers_part_03(state: ValidationState) -> None:
    expected_verification_input_ids = state.expected_verification_input_ids
    input_fingerprint_values = state.input_fingerprint_values
    result = state.result
    input_fingerprint_values.extend(
        _declared_values(
            result,
            (
                "input_fingerprints",
                "verification_source_separation_gate.input_fingerprints",
                "result.input_fingerprints",
            ),
        )
    )
    expected_input_fingerprints = input_fingerprint_values[0] if input_fingerprint_values else None
    expected_cycle_id = str(first_present(result, ["cycle_id", "result.cycle_id"]) or "").strip()
    expected_input_state_fingerprint = str(
        first_present(result, ["input_state_fingerprint", "result.input_state_fingerprint"])
        or ""
    ).strip()
    expected_attempt_identity = str(
        first_present(result, ["attempt_identity", "result.attempt_identity"]) or ""
    ).strip()
    expected_cohort_present = bool(list_values(expected_verification_input_ids)) or bool(
        expected_input_fingerprints
        if isinstance(expected_input_fingerprints, dict)
        else None
    )
    invalid_consumers: list[str] = []
    consumer_mismatches: dict[str, list[str]] = {}
    state.consumer_mismatches = consumer_mismatches
    state.expected_attempt_identity = expected_attempt_identity
    state.expected_cohort_present = expected_cohort_present
    state.expected_cycle_id = expected_cycle_id
    state.expected_input_fingerprints = expected_input_fingerprints
    state.expected_input_state_fingerprint = expected_input_state_fingerprint
    state.invalid_consumers = invalid_consumers


def _check_consumers_part_04(state: ValidationState) -> None:
    conformance_by_id = state.conformance_by_id
    consumer_mismatches = state.consumer_mismatches
    decision_identity = state.decision_identity
    expected_attempt_identity = state.expected_attempt_identity
    expected_body_fingerprint = state.expected_body_fingerprint
    expected_cohort_present = state.expected_cohort_present
    expected_cycle_id = state.expected_cycle_id
    expected_input_fingerprints = state.expected_input_fingerprints
    expected_input_state_fingerprint = state.expected_input_state_fingerprint
    expected_verification_input_ids = state.expected_verification_input_ids
    invalid_consumers = state.invalid_consumers
    required_consumer_ids = state.required_consumer_ids
    for consumer_id in required_consumer_ids:
        candidate_rows = conformance_by_id.get(str(consumer_id)) or []
        mismatched_fields: set[str] = set()

        def row_valid(row: dict[str, Any]) -> bool:
            row_mismatches: list[str] = []
            if not expected_cycle_id or row.get("cycle_id") != expected_cycle_id:
                row_mismatches.append("cycle_id")
            if (
                not _full_sha256(expected_input_state_fingerprint)
                or row.get("input_state_fingerprint") != expected_input_state_fingerprint
            ):
                row_mismatches.append("input_state_fingerprint")
            if not expected_attempt_identity or row.get("attempt_identity") != expected_attempt_identity:
                row_mismatches.append("attempt_identity")
            for field in ("artifact_id", "artifact_sha256", "production_lane_identity"):
                expected = decision_identity.get(field)
                if not non_empty(expected) or row.get(field) != expected:
                    row_mismatches.append(field)
            if not _full_sha256(expected_body_fingerprint):
                row_mismatches.append("body_projection_fingerprint")
            elif row.get("body_projection_fingerprint") != expected_body_fingerprint:
                row_mismatches.append("body_projection_fingerprint")
            if not expected_cohort_present:
                row_mismatches.append("source_cohort")
            if expected_verification_input_ids is not None:
                expected_ids = sorted(str(item) for item in list_values(expected_verification_input_ids))
                observed_ids = sorted(str(item) for item in list_values(row.get("verification_input_ids")))
                if observed_ids != expected_ids:
                    row_mismatches.append("verification_input_ids")
            if expected_input_fingerprints is not None and row.get("input_fingerprints") != expected_input_fingerprints:
                row_mismatches.append("input_fingerprints")
            mismatched_fields.update(row_mismatches)
            invocation_status = str(row.get("invocation_status") or "").strip().lower()
            return_status = str(row.get("return_contract_status") or "").strip().lower()
            echo_status = str(row.get("artifact_identity_echo_status") or "").strip().lower()
            consumption_status = str(row.get("decision_consumption_status") or "").strip().lower()
            return not row_mismatches and all(
                (
                    boolish(row.get("adapter_loaded")),
                    boolish(row.get("hook_resolved")),
                    boolish(row.get("hook_callable") or row.get("required_hook_callable")),
                    boolish(row.get("signature_bind_passed") or row.get("hook_signature_compatible")),
                    boolish(row.get("invocation_completed")) or invocation_status in {"complete", "completed", "pass", "passed", "success"},
                    boolish(row.get("return_contract_valid")) or return_status in {"valid", "pass", "passed"},
                    boolish(row.get("artifact_identity_echo_valid")) or echo_status in {"valid", "pass", "passed", "matched"},
                    boolish(row.get("value_consumed_by_decision")) or consumption_status in {"consumed", "pass", "passed"},
                    str(row.get("evidence_provenance") or "").strip().lower()
                    in {"independently_verified", "self_grounded"},
                    non_empty(row.get("probe_evidence_ref")),
                    _full_sha256(row.get("probe_evidence_sha256")),
                    str(row.get("probe_evidence_sha256") or "").lower()
                    == _consumer_receipt_binding_sha256(row),
                )
            )

        valid = bool(candidate_rows) and all(row_valid(row) for row in candidate_rows)
        if not valid:
            invalid_consumers.append(str(consumer_id))
            if mismatched_fields:
                consumer_mismatches[str(consumer_id)] = sorted(mismatched_fields)


def _check_consumers_part_05(state: ValidationState) -> None:
    consumer_mismatches = state.consumer_mismatches
    findings = state.findings
    invalid_consumers = state.invalid_consumers
    mode = state.mode
    target = state.target
    if invalid_consumers:
        add(
            findings,
            "block" if mode == "block" or target == "validate" else "warn",
            "required_consumer_context_not_evaluated",
            "Required adapter consumer contexts lack a full external invocation receipt; import, hook-name presence, or adapter self-attestation is insufficient.",
            {
                "consumer_context_ids": invalid_consumers,
                "mismatched_fields": consumer_mismatches or None,
            },
        )


def check_consumers(state: ValidationState) -> None:
    _check_consumers_part_01(state)
    _check_consumers_part_02(state)
    _check_consumers_part_03(state)
    _check_consumers_part_04(state)
    _check_consumers_part_05(state)
