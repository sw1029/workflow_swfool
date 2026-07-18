from __future__ import annotations

from typing import Any

from .constants import DURABLE_OPERATION_TYPES, SHA256_PATTERN
from .no_change_contract import validate_no_change_evidence
from .operation_owner_registry import validate_operation_owner_contract
from .support import canonical_sha256, validate_event_id


OPERATION_FIELDS = {
    "operation_id",
    "idempotency_key",
    "target_kind",
    "target_ref",
    "operation_kind",
    "expected_revision_id",
    "attempt_identity",
    "depends_on_operation_ids",
    "payload_schema_id",
    "payload_digest",
    "payload",
    "recovery_policy_id",
    # Compatibility aliases consumed by existing projection readers.
    "operation_type",
    "target_id",
    "payload_sha256",
}
TYPED_CANDIDATE_FIELDS = {
    "contract_version",
    "mode",
    "producer",
    "attempt_identity",
    "operations",
    "operation_ids",
    "expected_target_revision_ids",
    "operation_set_digest",
    "candidate_sha256",
}
NO_CHANGE_FIELDS = {
    "mode",
    "projections",
    "finalization_mode",
    "attempt_identity",
    "no_change_reason_id",
    "no_change_evidence",
    "no_change_evidence_digest",
}


def _identity_material(operation: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_kind": operation["target_kind"],
        "target_ref": operation["target_ref"],
        "operation_kind": operation["operation_kind"],
        "expected_revision_id": operation["expected_revision_id"],
        "attempt_identity": operation["attempt_identity"],
        "depends_on_operation_ids": operation["depends_on_operation_ids"],
        "payload_schema_id": operation["payload_schema_id"],
        "payload_digest": operation["payload_digest"],
        "recovery_policy_id": operation["recovery_policy_id"],
    }


def build_durable_operation(
    *,
    target_ref: str,
    operation_kind: str,
    attempt_identity: str,
    payload_schema_id: str,
    payload: dict[str, Any],
    expected_revision_id: str | None = None,
    depends_on_operation_ids: list[str] | None = None,
    target_kind: str = "projection",
    recovery_policy_id: str = "replay-or-reconcile",
) -> dict[str, Any]:
    operation = {
        "target_kind": validate_event_id(target_kind),
        "target_ref": validate_event_id(target_ref),
        "operation_kind": validate_event_id(operation_kind),
        "expected_revision_id": (
            validate_event_id(expected_revision_id)
            if expected_revision_id is not None
            else None
        ),
        "attempt_identity": validate_event_id(attempt_identity),
        "depends_on_operation_ids": [
            validate_event_id(value) for value in (depends_on_operation_ids or [])
        ],
        "payload_schema_id": validate_event_id(payload_schema_id),
        "payload_digest": canonical_sha256(payload),
        "payload": payload,
        "recovery_policy_id": validate_event_id(recovery_policy_id),
    }
    validate_operation_owner_contract(
        target_ref=operation["target_ref"],
        target_kind=operation["target_kind"],
        payload_schema_id=operation["payload_schema_id"],
        operation_kind=operation["operation_kind"],
        recovery_policy_id=operation["recovery_policy_id"],
        payload=operation["payload"],
    )
    identity_digest = canonical_sha256(_identity_material(operation))
    operation.update(
        {
            "operation_id": f"operation-{identity_digest}",
            "idempotency_key": f"idempotency-{identity_digest}",
            "operation_type": operation["operation_kind"],
            "target_id": operation["target_ref"],
            "payload_sha256": operation["payload_digest"],
        }
    )
    return operation


def build_typed_operations_candidate(
    *,
    producer: str,
    attempt_identity: str,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "contract_version": 2,
        "mode": "typed_operations",
        "producer": validate_event_id(producer),
        "attempt_identity": validate_event_id(attempt_identity),
        "operations": operations,
        "operation_ids": [operation.get("operation_id") for operation in operations],
        "expected_target_revision_ids": [
            operation.get("expected_revision_id") for operation in operations
        ],
        "operation_set_digest": canonical_sha256(operations),
    }
    candidate["candidate_sha256"] = canonical_sha256(candidate)
    return candidate


def build_no_durable_state_change_candidate(
    *, attempt_identity: str, reason_id: str, evidence: dict[str, Any]
) -> dict[str, Any]:
    attempt = validate_event_id(attempt_identity)
    reason = validate_event_id(reason_id)
    validated_evidence = validate_no_change_evidence(
        evidence,
        reason_id=reason,
        attempt_identity=attempt,
    )
    evidence_digest = canonical_sha256(
        {
            "attempt_identity": attempt,
            "finalization_mode": "no_durable_state_change",
            "no_change_reason_id": reason,
            "no_change_evidence": validated_evidence,
            "projections": {},
        }
    )
    return {
        "mode": "complete_projection",
        "projections": {},
        "finalization_mode": "no_durable_state_change",
        "attempt_identity": attempt,
        "no_change_reason_id": reason,
        "no_change_evidence": validated_evidence,
        "no_change_evidence_digest": evidence_digest,
    }


def validate_no_change_candidate(
    durable_state: dict[str, Any], *, attempt_identity: str
) -> None:
    if set(durable_state) != NO_CHANGE_FIELDS or durable_state.get("projections") != {}:
        raise ValueError(
            "complete_projection is reserved for an exact no_durable_state_change receipt"
        )
    if durable_state.get("finalization_mode") != "no_durable_state_change":
        raise ValueError(
            "empty durable state requires finalization_mode no_durable_state_change"
        )
    if durable_state.get("attempt_identity") != attempt_identity:
        raise ValueError("no-change durable state attempt identity mismatch")
    raw_reason_id = durable_state.get("no_change_reason_id")
    reason_id = validate_event_id(raw_reason_id)
    if not isinstance(raw_reason_id, str) or raw_reason_id != reason_id:
        raise ValueError("no-change reason_id must be an exact opaque string ID")
    evidence = validate_no_change_evidence(
        durable_state.get("no_change_evidence"),
        reason_id=reason_id,
        attempt_identity=attempt_identity,
    )
    expected = canonical_sha256(
        {
            "attempt_identity": attempt_identity,
            "finalization_mode": "no_durable_state_change",
            "no_change_reason_id": reason_id,
            "no_change_evidence": evidence,
            "projections": {},
        }
    )
    evidence_digest = durable_state.get("no_change_evidence_digest")
    if (
        not isinstance(evidence_digest, str)
        or not SHA256_PATTERN.fullmatch(evidence_digest)
        or evidence_digest != expected
    ):
        raise ValueError("no-change durable state evidence digest mismatch")


def validate_typed_operations_candidate(
    durable_state: dict[str, Any], *, attempt_identity: str
) -> None:
    if set(durable_state) != TYPED_CANDIDATE_FIELDS:
        raise ValueError(
            "typed_operations candidate fields do not match contract version 2"
        )
    if durable_state.get("contract_version") != 2:
        raise ValueError("typed_operations contract_version must be 2")
    if durable_state.get("mode") != "typed_operations":
        raise ValueError("typed operations candidate mode mismatch")
    validate_event_id(durable_state.get("producer"))
    if durable_state.get("attempt_identity") != attempt_identity:
        raise ValueError("typed operation attempt identity mismatch")
    operations = durable_state.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError(
            "typed_operations durable state requires a non-empty operations list"
        )
    seen_operations: set[str] = set()
    seen_idempotency: set[str] = set()
    seen_targets: set[str] = set()
    for index, operation in enumerate(operations):
        _validate_operation(
            operation,
            index=index,
            attempt_identity=attempt_identity,
            prior_operation_ids=seen_operations,
        )
        operation_id = operation["operation_id"]
        if operation_id in seen_operations:
            raise ValueError(
                f"durable state operation_id is duplicated: {operation_id}"
            )
        if operation["idempotency_key"] in seen_idempotency:
            raise ValueError("durable state idempotency_key is duplicated")
        if operation["target_ref"] in seen_targets:
            raise ValueError(
                f"durable state operation target_ref is duplicated: {operation['target_ref']}"
            )
        seen_operations.add(operation_id)
        seen_idempotency.add(operation["idempotency_key"])
        seen_targets.add(operation["target_ref"])
    if durable_state.get("operation_ids") != [
        operation["operation_id"] for operation in operations
    ]:
        raise ValueError("typed operation_ids must preserve exact dependency order")
    if durable_state.get("expected_target_revision_ids") != [
        operation["expected_revision_id"] for operation in operations
    ]:
        raise ValueError("typed expected target revisions do not match operations")
    if durable_state.get("operation_set_digest") != canonical_sha256(operations):
        raise ValueError("typed operation_set_digest mismatch")
    candidate_body = dict(durable_state)
    candidate_digest = candidate_body.pop("candidate_sha256", None)
    if candidate_digest != canonical_sha256(candidate_body):
        raise ValueError("durable state candidate_sha256 mismatch")


def _validate_operation(
    operation: object,
    *,
    index: int,
    attempt_identity: str,
    prior_operation_ids: set[str],
) -> None:
    if not isinstance(operation, dict) or set(operation) != OPERATION_FIELDS:
        raise ValueError(f"durable state operation {index} fields are invalid")
    for field in (
        "operation_id",
        "idempotency_key",
        "target_kind",
        "target_ref",
        "operation_kind",
        "attempt_identity",
        "payload_schema_id",
        "recovery_policy_id",
    ):
        validate_event_id(operation.get(field))
    if operation["operation_kind"] not in DURABLE_OPERATION_TYPES:
        raise ValueError(
            f"durable state operation {index} has an unsupported operation_kind"
        )
    validate_operation_owner_contract(
        target_ref=operation["target_ref"],
        target_kind=operation["target_kind"],
        payload_schema_id=operation["payload_schema_id"],
        operation_kind=operation["operation_kind"],
        recovery_policy_id=operation["recovery_policy_id"],
        payload=operation["payload"],
    )
    if operation["operation_type"] != operation["operation_kind"]:
        raise ValueError("durable operation kind alias mismatch")
    if operation["target_id"] != operation["target_ref"]:
        raise ValueError("durable operation target alias mismatch")
    if operation["attempt_identity"] != attempt_identity:
        raise ValueError("durable operation attempt identity mismatch")
    expected_revision = operation.get("expected_revision_id")
    if expected_revision is not None:
        validate_event_id(expected_revision)
    dependencies = operation.get("depends_on_operation_ids")
    if (
        not isinstance(dependencies, list)
        or len(dependencies) != len(set(dependencies))
        or any(
            validate_event_id(value) not in prior_operation_ids
            for value in dependencies
        )
    ):
        raise ValueError(
            "durable operation dependencies must be unique earlier operations"
        )
    payload = operation.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"durable state operation {index} requires object payload")
    payload_digest = operation.get("payload_digest")
    if (
        not isinstance(payload_digest, str)
        or not SHA256_PATTERN.fullmatch(payload_digest)
        or payload_digest != canonical_sha256(payload)
        or operation.get("payload_sha256") != payload_digest
    ):
        raise ValueError(f"durable state operation {index} payload digest mismatch")
    identity_digest = canonical_sha256(_identity_material(operation))
    if operation["operation_id"] != f"operation-{identity_digest}":
        raise ValueError("durable operation_id is not content-bound")
    if operation["idempotency_key"] != f"idempotency-{identity_digest}":
        raise ValueError("durable idempotency_key is not attempt/payload-bound")


def target_revision_ids(durable_state: dict[str, Any]) -> dict[str, str]:
    if durable_state.get("mode") != "typed_operations":
        return {}
    return {
        operation["target_ref"]: f"sha256-{operation['payload_digest']}"
        for operation in durable_state.get("operations") or []
        if isinstance(operation, dict)
    }


def projected_target_state(durable_state: dict[str, Any]) -> dict[str, Any]:
    if durable_state.get("mode") != "typed_operations":
        return {}
    return {
        operation["target_ref"]: {
            "target_kind": operation["target_kind"],
            "operation_kind": operation["operation_kind"],
            "operation_id": operation["operation_id"],
            "idempotency_key": operation["idempotency_key"],
            "payload_schema_id": operation["payload_schema_id"],
            "payload_digest": operation["payload_digest"],
            "resulting_revision_id": f"sha256-{operation['payload_digest']}",
            "payload": operation["payload"],
        }
        for operation in durable_state.get("operations") or []
        if isinstance(operation, dict)
    }


__all__ = [
    "build_durable_operation",
    "build_no_durable_state_change_candidate",
    "build_typed_operations_candidate",
    "projected_target_state",
    "target_revision_ids",
    "validate_no_change_candidate",
    "validate_typed_operations_candidate",
]
