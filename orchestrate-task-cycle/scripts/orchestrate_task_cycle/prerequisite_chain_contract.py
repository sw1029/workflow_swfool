"""Shared, content-bound contract for bounded prerequisite chains.

The task-pack validator and derive result validator deliberately use this one
implementation.  A caller-authored decreasing scalar is trace data; it does
not establish strict reduction without a closed observation receipt.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .result_contract.task_routing import (
    DECISION_FRESHNESS_TASK_KINDS,
    EXECUTION_PRODUCING_TASK_KINDS,
    PRODUCER_RECONCILIATION_TASK_KINDS,
    PRODUCER_SUPPLY_TASK_KINDS,
    normalize_task_kind,
)


APPLICABILITY = {"applicable", "not_applicable"}
TRISTATE = {True, False, "not_evaluated"}
BUDGET_STATUSES = {"within", "exhausted", "budget_unverified", "not_evaluated"}
DIRECT_SUCCESSOR_KINDS = {
    "producer",
    "implementation",
    "regenerate_or_refresh_output",
    "descope",
    "terminal",
}
SUCCESSOR_KINDS = DIRECT_SUCCESSOR_KINDS | {"none"}

_FULL_SHA256 = re.compile(r"[0-9a-f]{64}")
_OBSERVATION_FIELDS = {
    "observation_id",
    "revision_id",
    "value",
    "evidence_ref_id",
    "evidence_sha256",
}
_REDUCTION_RECEIPT_FIELDS = {
    "contract_version",
    "receipt_id",
    "stable_root_id",
    "prerequisite_relation_id",
    "residual_basis_id",
    "observation_kind",
    "before_observation",
    "after_observation",
    "source_kind",
    "source_revision_sha256",
    "source_snapshot_sha256",
    "observer_id",
    "invariant_owner_id",
    "provenance_status",
    "receipt_sha256",
}
_NOT_APPLICABLE_FIELDS = {
    "contract_version",
    "reason_id",
    "subject_id",
    "evidence_ref_id",
    "evidence_sha256",
    "receipt_sha256",
}

_PRODUCER_TASK_KINDS = (
    PRODUCER_SUPPLY_TASK_KINDS
    | EXECUTION_PRODUCING_TASK_KINDS
    | PRODUCER_RECONCILIATION_TASK_KINDS
    | {"producer"}
)
_IMPLEMENTATION_TASK_KINDS = {
    "implementation",
    "implementation_execution",
    "implementation_repair",
    "direct_implementation",
    "logic_repair",
    "direct_logic_repair",
    "code_repair",
    "code_contract_repair",
    "schema_repair",
}
_REFRESH_TASK_KINDS = {
    kind
    for kind in DECISION_FRESHNESS_TASK_KINDS
    if "refresh" in kind
    or "measurement" in kind
    or "rerun" in kind
    or "revalidation" in kind
} | {"regenerate_or_refresh_output", "output_regeneration", "output_refresh"}
_DESCOPE_TASK_KINDS = {"descope", "residual_descope", "descope_with_residual"}
_TERMINAL_TASK_KINDS = {
    "terminal",
    "terminal_blocked",
    "terminal_blocker",
    "user_escalation",
}
_CATEGORY_TASK_KINDS = {
    "producer": _PRODUCER_TASK_KINDS,
    "implementation": _IMPLEMENTATION_TASK_KINDS,
    "regenerate_or_refresh_output": _REFRESH_TASK_KINDS,
    "descope": _DESCOPE_TASK_KINDS,
    "terminal": _TERMINAL_TASK_KINDS,
}


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def receipt_sha256(receipt: dict[str, Any]) -> str:
    return canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )


def _nonempty_token(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _full_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(_FULL_SHA256.fullmatch(value))


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _observation_valid(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != _OBSERVATION_FIELDS:
        return False
    return (
        all(
            _nonempty_token(value.get(field))
            for field in ("observation_id", "revision_id", "evidence_ref_id")
        )
        and _full_sha256(value.get("evidence_sha256"))
        and _number(value.get("value")) is not None
    )


def reduction_observation_valid(raw: dict[str, Any]) -> bool:
    """Independently recompute strict reduction from a closed source receipt."""

    receipt = raw.get("reduction_observation_receipt")
    if not isinstance(receipt, dict) or set(receipt) != _REDUCTION_RECEIPT_FIELDS:
        return False
    if receipt.get("contract_version") != "prerequisite-reduction-observation-v1":
        return False
    if not all(
        _nonempty_token(receipt.get(field))
        for field in (
            "receipt_id",
            "stable_root_id",
            "prerequisite_relation_id",
            "residual_basis_id",
            "observer_id",
            "invariant_owner_id",
        )
    ):
        return False
    if receipt.get("stable_root_id") != raw.get("stable_root_id"):
        return False
    if receipt.get("prerequisite_relation_id") != raw.get("prerequisite_relation_id"):
        return False
    if receipt.get("observation_kind") not in {"residual", "unresolved_owner_count"}:
        return False
    if receipt.get("source_kind") not in {"task_pack_projection", "repository_adapter"}:
        return False
    if receipt.get("provenance_status") != "independently_observed":
        return False
    if not all(
        _full_sha256(receipt.get(field))
        for field in (
            "source_revision_sha256",
            "source_snapshot_sha256",
            "receipt_sha256",
        )
    ):
        return False
    before = receipt.get("before_observation")
    after = receipt.get("after_observation")
    if not _observation_valid(before) or not _observation_valid(after):
        return False
    if (
        before["observation_id"] == after["observation_id"]
        or before["revision_id"] == after["revision_id"]
    ):
        return False
    if receipt.get("receipt_sha256") != receipt_sha256(receipt):
        return False
    before_value = _number(before["value"])
    after_value = _number(after["value"])
    if before_value is None or after_value is None or after_value >= before_value:
        return False
    if receipt["observation_kind"] == "residual":
        return (
            _number(raw.get("residual_before")) == before_value
            and _number(raw.get("residual_after")) == after_value
        )
    return (
        _number(raw.get("unresolved_owner_count_before")) == before_value
        and _number(raw.get("unresolved_owner_count_after")) == after_value
    )


def not_applicable_evidence_valid(raw: dict[str, Any]) -> bool:
    receipt = raw.get("not_applicable_evidence")
    if not isinstance(receipt, dict) or set(receipt) != _NOT_APPLICABLE_FIELDS:
        return False
    return (
        receipt.get("contract_version") == "prerequisite-not-applicable-v1"
        and all(
            _nonempty_token(receipt.get(field))
            for field in ("reason_id", "subject_id", "evidence_ref_id")
        )
        and _full_sha256(receipt.get("evidence_sha256"))
        and _full_sha256(receipt.get("receipt_sha256"))
        and receipt.get("receipt_sha256") == receipt_sha256(receipt)
    )


def successor_task_kind_valid(successor_kind: str, selected_task_kind: str) -> bool:
    kind = normalize_task_kind(selected_task_kind)
    return bool(kind and kind in _CATEGORY_TASK_KINDS.get(successor_kind, set()))


__all__ = [
    "APPLICABILITY",
    "BUDGET_STATUSES",
    "DIRECT_SUCCESSOR_KINDS",
    "SUCCESSOR_KINDS",
    "TRISTATE",
    "canonical_sha256",
    "not_applicable_evidence_valid",
    "receipt_sha256",
    "reduction_observation_valid",
    "successor_task_kind_valid",
]
