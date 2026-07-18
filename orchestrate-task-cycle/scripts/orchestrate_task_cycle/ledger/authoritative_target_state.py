from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .operation_owner_registry import (
    REGISTERED_DURABLE_TARGETS,
    registered_target_owner_id,
    validate_registered_target_ref,
)
from .support import canonical_sha256, validate_event_id


TARGET_PROJECTION_FIELDS = frozenset(
    {
        "target_kind",
        "operation_kind",
        "operation_id",
        "idempotency_key",
        "payload_schema_id",
        "payload_digest",
        "resulting_revision_id",
        "payload",
    }
)


@dataclass(frozen=True)
class AuthoritativeTargetState:
    owner_id: str
    state_status: str
    revision_id: str
    state_digest: str


def absent_registered_target_state_digest(target_ref: str) -> str:
    target = validate_registered_target_ref(validate_event_id(target_ref))
    return canonical_sha256({"state": "absent", "target_ref": target})


def _present_target_state(
    target_ref: str,
    projection: object,
) -> AuthoritativeTargetState:
    if not isinstance(projection, dict) or set(projection) != TARGET_PROJECTION_FIELDS:
        raise ValueError(
            f"authoritative target projection fields are invalid for {target_ref}"
        )
    registration = REGISTERED_DURABLE_TARGETS[target_ref]
    if projection["target_kind"] != registration.target_kind:
        raise ValueError(
            f"authoritative target_kind is not owner-registered for {target_ref}"
        )
    if projection["operation_kind"] not in registration.operation_kinds:
        raise ValueError(
            f"authoritative operation_kind is not owner-registered for {target_ref}"
        )
    schema_id = projection["payload_schema_id"]
    payload_validator = registration.payload_validators.get(schema_id)
    if payload_validator is None:
        raise ValueError(
            f"authoritative payload_schema_id is not owner-registered for {target_ref}"
        )
    validate_event_id(projection["operation_id"])
    validate_event_id(projection["idempotency_key"])
    payload = projection["payload"]
    payload_validator(payload)
    payload_digest = canonical_sha256(payload)
    if projection["payload_digest"] != payload_digest:
        raise ValueError(
            f"authoritative target payload digest mismatch for {target_ref}"
        )
    revision_id = f"sha256-{payload_digest}"
    if projection["resulting_revision_id"] != revision_id:
        raise ValueError(f"authoritative target revision mismatch for {target_ref}")
    return AuthoritativeTargetState(
        owner_id=registration.owner_id,
        state_status="present",
        revision_id=revision_id,
        state_digest=payload_digest,
    )


def current_registered_target_state(
    target_ref: str,
    authoritative_projection: dict[str, Any],
) -> AuthoritativeTargetState:
    """Resolve one exact registered target without consulting sibling owners."""
    target = validate_registered_target_ref(validate_event_id(target_ref))
    if target not in authoritative_projection:
        return AuthoritativeTargetState(
            owner_id=registered_target_owner_id(target),
            state_status="absent",
            revision_id="absent",
            state_digest=absent_registered_target_state_digest(target),
        )
    return _present_target_state(target, authoritative_projection[target])


__all__ = [
    "AuthoritativeTargetState",
    "TARGET_PROJECTION_FIELDS",
    "absent_registered_target_state_digest",
    "current_registered_target_state",
]
