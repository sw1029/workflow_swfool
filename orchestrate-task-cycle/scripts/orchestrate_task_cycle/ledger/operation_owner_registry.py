from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping

from .payload_schemas_core import (
    validate_dedup_symbol_registry_payload,
    validate_ledger_projection_payload,
    validate_registry_projection_payload,
)
from .payload_schemas_loopback import (
    validate_family_progress_registry_payload,
    validate_recurrence_identity_payload,
    validate_root_cause_ledger_payload,
    validate_sealed_blocker_families_payload,
)


PayloadValidator = Callable[[object], None]


@dataclass(frozen=True)
class DurableTargetRegistration:
    owner_id: str
    target_kind: str
    payload_validators: Mapping[str, PayloadValidator]
    operation_kinds: frozenset[str]
    recovery_policy_ids: frozenset[str]

    @property
    def payload_schema_ids(self) -> frozenset[str]:
        return frozenset(self.payload_validators)


_REPLACE_ONLY = frozenset({"replace_projection"})
_REPLACE_OR_APPEND = frozenset({"replace_projection", "append_projection"})
_REPLAY_OR_RECONCILE = frozenset({"replay-or-reconcile"})


def _payload_schema(
    schema_id: str,
    validator: PayloadValidator,
) -> Mapping[str, PayloadValidator]:
    return MappingProxyType({schema_id: validator})


REGISTERED_DURABLE_TARGETS: Mapping[str, DurableTargetRegistration] = MappingProxyType(
    {
        "registry_projection": DurableTargetRegistration(
            owner_id="cycle-finalization-owner",
            target_kind="projection",
            payload_validators=_payload_schema(
                "registry-projection-v1",
                validate_registry_projection_payload,
            ),
            operation_kinds=_REPLACE_ONLY,
            recovery_policy_ids=_REPLAY_OR_RECONCILE,
        ),
        "ledger_projection": DurableTargetRegistration(
            owner_id="cycle-finalization-owner",
            target_kind="projection",
            payload_validators=_payload_schema(
                "ledger-projection-v1",
                validate_ledger_projection_payload,
            ),
            operation_kinds=_REPLACE_OR_APPEND,
            recovery_policy_ids=_REPLAY_OR_RECONCILE,
        ),
        "family_progress_registry": DurableTargetRegistration(
            owner_id="audit-cycle-loopback",
            target_kind="projection",
            payload_validators=_payload_schema(
                "family-progress-registry-v1",
                validate_family_progress_registry_payload,
            ),
            operation_kinds=_REPLACE_ONLY,
            recovery_policy_ids=_REPLAY_OR_RECONCILE,
        ),
        "root_cause_ledger": DurableTargetRegistration(
            owner_id="audit-cycle-loopback",
            target_kind="projection",
            payload_validators=_payload_schema(
                "root-cause-ledger-v1",
                validate_root_cause_ledger_payload,
            ),
            operation_kinds=_REPLACE_OR_APPEND,
            recovery_policy_ids=_REPLAY_OR_RECONCILE,
        ),
        "sealed_blocker_families": DurableTargetRegistration(
            owner_id="audit-cycle-loopback",
            target_kind="projection",
            payload_validators=_payload_schema(
                "sealed-blocker-families-v1",
                validate_sealed_blocker_families_payload,
            ),
            operation_kinds=_REPLACE_ONLY,
            recovery_policy_ids=_REPLAY_OR_RECONCILE,
        ),
        "recurrence_identity": DurableTargetRegistration(
            owner_id="audit-cycle-loopback",
            target_kind="projection",
            payload_validators=_payload_schema(
                "recurrence-identity-v1",
                validate_recurrence_identity_payload,
            ),
            operation_kinds=_REPLACE_ONLY,
            recovery_policy_ids=_REPLAY_OR_RECONCILE,
        ),
        "dedup_symbol_registry": DurableTargetRegistration(
            owner_id="progress-loop-detection",
            target_kind="projection",
            payload_validators=_payload_schema(
                "dedup-symbol-registry-v1",
                validate_dedup_symbol_registry_payload,
            ),
            operation_kinds=_REPLACE_ONLY,
            recovery_policy_ids=_REPLAY_OR_RECONCILE,
        ),
    }
)


def validate_operation_owner_contract(
    *,
    target_ref: str,
    target_kind: str,
    payload_schema_id: str,
    operation_kind: str,
    recovery_policy_id: str,
    payload: object,
) -> DurableTargetRegistration:
    registration = REGISTERED_DURABLE_TARGETS.get(target_ref)
    if registration is None:
        raise ValueError(f"durable target_ref is not owner-registered: {target_ref}")
    if target_kind != registration.target_kind:
        raise ValueError(
            f"durable target_kind is not registered for {target_ref}: {target_kind}"
        )
    payload_validator = registration.payload_validators.get(payload_schema_id)
    if payload_validator is None:
        raise ValueError(
            f"durable payload_schema_id is not owner-registered for {target_ref}: "
            f"{payload_schema_id}"
        )
    if operation_kind not in registration.operation_kinds:
        raise ValueError(
            f"durable operation_kind is not owner-registered for {target_ref}: "
            f"{operation_kind}"
        )
    if recovery_policy_id not in registration.recovery_policy_ids:
        raise ValueError(
            f"durable recovery_policy_id is not owner-registered for {target_ref}: "
            f"{recovery_policy_id}"
        )
    payload_validator(payload)
    return registration


def validate_registered_target_ref(target_ref: str) -> str:
    if target_ref not in REGISTERED_DURABLE_TARGETS:
        raise ValueError(
            f"no-change evidence target_ref is not owner-registered: {target_ref}"
        )
    return target_ref


def registered_target_owner_id(target_ref: str) -> str:
    validate_registered_target_ref(target_ref)
    return REGISTERED_DURABLE_TARGETS[target_ref].owner_id


__all__ = [
    "DurableTargetRegistration",
    "REGISTERED_DURABLE_TARGETS",
    "PayloadValidator",
    "registered_target_owner_id",
    "validate_operation_owner_contract",
    "validate_registered_target_ref",
]
