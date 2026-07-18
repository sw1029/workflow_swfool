from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .authoritative_target_state import (
    absent_registered_target_state_digest,
    current_registered_target_state,
)
from .constants import SHA256_PATTERN
from .operation_owner_registry import (
    registered_target_owner_id,
    validate_registered_target_ref,
)
from .support import canonical_sha256, validate_event_id


TARGET_OBSERVATION_FIELDS = {
    "contract_version",
    "observation_kind",
    "observation_id",
    "attempt_identity",
    "target_ref",
    "owner_id",
    "state_status",
    "before_revision_id",
    "current_revision_id",
    "before_state_digest",
    "current_state_digest",
    "observation_receipt_sha256",
}
NO_CHANGE_EVIDENCE_FIELDS = {
    "contract_version",
    "evidence_kind",
    "producer_stage",
    "evidence_id",
    "attempt_identity",
    "target_inventory_status",
    "evaluated_target_ids",
    "target_observations",
    "changed_target_ids",
    "evidence_sha256",
}


@dataclass(frozen=True)
class NoChangeReasonRegistration:
    evidence_kind: str
    producer_stage: str
    inventory_statuses: frozenset[str]


REGISTERED_NO_CHANGE_REASONS: Mapping[str, NoChangeReasonRegistration] = (
    MappingProxyType(
        {
            "validation-has-no-durable-axis-change": NoChangeReasonRegistration(
                evidence_kind="validated-no-durable-axis-change",
                producer_stage="validate",
                inventory_statuses=frozenset({"evaluated_unchanged"}),
            )
        }
    )
)


def _exact_event_id(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"no-change {field} must be an exact opaque string ID")
    normalized = validate_event_id(value)
    if normalized != value:
        raise ValueError(f"no-change {field} must not require normalization")
    return normalized


def _exact_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"no-change {field} must be a full lowercase SHA-256 digest")
    return value


def absent_target_state_digest(target_ref: str) -> str:
    return absent_registered_target_state_digest(target_ref)


def build_unchanged_target_observation(
    *,
    observation_id: str,
    attempt_identity: str,
    target_ref: str,
    state_status: str,
    before_revision_id: str,
    current_revision_id: str,
    before_state_digest: str,
    current_state_digest: str,
) -> dict[str, Any]:
    target = validate_registered_target_ref(validate_event_id(target_ref))
    observation: dict[str, Any] = {
        "contract_version": 1,
        "observation_kind": "registered-owner-target-state-observation",
        "observation_id": validate_event_id(observation_id),
        "attempt_identity": validate_event_id(attempt_identity),
        "target_ref": target,
        "owner_id": registered_target_owner_id(target),
        "state_status": validate_event_id(state_status),
        "before_revision_id": validate_event_id(before_revision_id),
        "current_revision_id": validate_event_id(current_revision_id),
        "before_state_digest": before_state_digest,
        "current_state_digest": current_state_digest,
    }
    _validate_target_observation_body(
        observation,
        attempt_identity=observation["attempt_identity"],
    )
    observation["observation_receipt_sha256"] = canonical_sha256(observation)
    return observation


def build_no_change_evidence(
    *,
    evidence_id: str,
    attempt_identity: str,
    target_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    attempt = validate_event_id(attempt_identity)
    observations = _validate_target_observations(
        target_observations,
        attempt_identity=attempt,
    )
    evidence: dict[str, Any] = {
        "contract_version": 1,
        "evidence_kind": "validated-no-durable-axis-change",
        "producer_stage": "validate",
        "evidence_id": validate_event_id(evidence_id),
        "attempt_identity": attempt,
        "target_inventory_status": "evaluated_unchanged",
        "evaluated_target_ids": [row["target_ref"] for row in observations],
        "target_observations": observations,
        "changed_target_ids": [],
    }
    evidence["evidence_sha256"] = canonical_sha256(evidence)
    return evidence


def validate_no_change_evidence(
    evidence: object,
    *,
    reason_id: str,
    attempt_identity: str,
) -> dict[str, Any]:
    registration = REGISTERED_NO_CHANGE_REASONS.get(reason_id)
    if registration is None:
        raise ValueError(f"no-change reason_id is not registered: {reason_id}")
    if not isinstance(evidence, dict) or set(evidence) != NO_CHANGE_EVIDENCE_FIELDS:
        raise ValueError("no-change evidence fields do not match contract version 1")
    if evidence.get("contract_version") != 1:
        raise ValueError("no-change evidence contract_version must be 1")
    if evidence.get("evidence_kind") != registration.evidence_kind:
        raise ValueError("no-change reason/evidence_kind relation mismatch")
    if evidence.get("producer_stage") != registration.producer_stage:
        raise ValueError("no-change reason/producer_stage relation mismatch")
    _exact_event_id(evidence.get("evidence_id"), field="evidence_id")
    evidence_attempt = _exact_event_id(
        evidence.get("attempt_identity"),
        field="evidence attempt_identity",
    )
    if evidence_attempt != attempt_identity:
        raise ValueError("no-change evidence attempt identity mismatch")
    inventory_status = _exact_event_id(
        evidence.get("target_inventory_status"),
        field="target_inventory_status",
    )
    if inventory_status not in registration.inventory_statuses:
        raise ValueError("no-change reason/target inventory relation mismatch")
    observations = _validate_target_observations(
        evidence.get("target_observations"),
        attempt_identity=attempt_identity,
    )
    evaluated_target_ids = evidence.get("evaluated_target_ids")
    if evaluated_target_ids != [row["target_ref"] for row in observations]:
        raise ValueError("no-change target inventory does not match owner observations")
    if evidence.get("changed_target_ids") != []:
        raise ValueError("no-change evidence must report zero changed_target_ids")
    evidence_sha256 = evidence.get("evidence_sha256")
    evidence_body = {
        key: value for key, value in evidence.items() if key != "evidence_sha256"
    }
    if (
        not isinstance(evidence_sha256, str)
        or not SHA256_PATTERN.fullmatch(evidence_sha256)
        or evidence_sha256 != canonical_sha256(evidence_body)
    ):
        raise ValueError("no-change evidence_sha256 is not content-bound")
    return evidence


def no_change_candidate_matches_authoritative_state(
    durable_state: dict[str, Any],
    authoritative_projection: dict[str, Any],
) -> bool:
    """Compare every claimed unchanged target with its exact current owner state."""
    if durable_state.get("finalization_mode") != "no_durable_state_change":
        return True
    evidence = durable_state.get("no_change_evidence")
    if not isinstance(evidence, dict):
        return False
    observations = evidence.get("target_observations")
    if not isinstance(observations, list):
        return False
    for observation in observations:
        if not isinstance(observation, dict):
            return False
        actual = current_registered_target_state(
            observation["target_ref"],
            authoritative_projection,
        )
        if (
            observation.get("owner_id") != actual.owner_id
            or observation.get("state_status") != actual.state_status
            or observation.get("current_revision_id") != actual.revision_id
            or observation.get("current_state_digest") != actual.state_digest
        ):
            return False
    return True


def _validate_target_observations(
    observations: object,
    *,
    attempt_identity: str,
) -> list[dict[str, Any]]:
    if not isinstance(observations, list) or not observations:
        raise ValueError(
            "no-change evidence requires non-empty registered owner target observations"
        )
    targets: set[str] = set()
    observation_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError("no-change target observation must be an object")
        _validate_target_observation(
            observation,
            attempt_identity=attempt_identity,
        )
        target_ref = observation["target_ref"]
        observation_id = observation["observation_id"]
        if target_ref in targets or observation_id in observation_ids:
            raise ValueError("no-change target observations must be unique")
        targets.add(target_ref)
        observation_ids.add(observation_id)
        validated.append(observation)
    return validated


def _validate_target_observation(
    observation: dict[str, Any],
    *,
    attempt_identity: str,
) -> None:
    if set(observation) != TARGET_OBSERVATION_FIELDS:
        raise ValueError("no-change target observation fields do not match contract")
    _validate_target_observation_body(
        observation,
        attempt_identity=attempt_identity,
    )
    receipt = observation.get("observation_receipt_sha256")
    receipt_body = {
        key: value
        for key, value in observation.items()
        if key != "observation_receipt_sha256"
    }
    if (
        not isinstance(receipt, str)
        or not SHA256_PATTERN.fullmatch(receipt)
        or receipt != canonical_sha256(receipt_body)
    ):
        raise ValueError("no-change target observation receipt is not content-bound")


def _validate_target_observation_body(
    observation: dict[str, Any],
    *,
    attempt_identity: str,
) -> None:
    if observation.get("contract_version") != 1:
        raise ValueError("no-change target observation contract_version must be 1")
    if (
        observation.get("observation_kind")
        != "registered-owner-target-state-observation"
    ):
        raise ValueError("no-change target observation kind is invalid")
    _exact_event_id(observation.get("observation_id"), field="observation_id")
    observed_attempt = _exact_event_id(
        observation.get("attempt_identity"),
        field="observation attempt_identity",
    )
    if observed_attempt != attempt_identity:
        raise ValueError("no-change target observation attempt mismatch")
    target_ref = _exact_event_id(
        observation.get("target_ref"),
        field="observation target_ref",
    )
    validate_registered_target_ref(target_ref)
    if observation.get("owner_id") != registered_target_owner_id(target_ref):
        raise ValueError("no-change target observation owner mismatch")
    state_status = _exact_event_id(
        observation.get("state_status"),
        field="observation state_status",
    )
    before_revision = _exact_event_id(
        observation.get("before_revision_id"),
        field="before_revision_id",
    )
    current_revision = _exact_event_id(
        observation.get("current_revision_id"),
        field="current_revision_id",
    )
    before_digest = _exact_digest(
        observation.get("before_state_digest"),
        field="before_state_digest",
    )
    current_digest = _exact_digest(
        observation.get("current_state_digest"),
        field="current_state_digest",
    )
    if before_revision != current_revision or before_digest != current_digest:
        raise ValueError("no-change target observation reports a state change")
    _validate_revision_digest_relation(
        target_ref=target_ref,
        state_status=state_status,
        revision_id=current_revision,
        state_digest=current_digest,
    )


def _validate_revision_digest_relation(
    *,
    target_ref: str,
    state_status: str,
    revision_id: str,
    state_digest: str,
) -> None:
    if state_status == "present":
        if revision_id != f"sha256-{state_digest}":
            raise ValueError(
                "no-change present target revision/digest relation mismatch"
            )
        return
    if state_status == "absent":
        if revision_id != "absent" or state_digest != absent_target_state_digest(
            target_ref
        ):
            raise ValueError(
                "no-change absent target revision/digest relation mismatch"
            )
        return
    raise ValueError("no-change target observation state_status is invalid")


__all__ = [
    "NO_CHANGE_EVIDENCE_FIELDS",
    "REGISTERED_NO_CHANGE_REASONS",
    "TARGET_OBSERVATION_FIELDS",
    "absent_target_state_digest",
    "build_no_change_evidence",
    "build_unchanged_target_observation",
    "no_change_candidate_matches_authoritative_state",
    "validate_no_change_evidence",
]
