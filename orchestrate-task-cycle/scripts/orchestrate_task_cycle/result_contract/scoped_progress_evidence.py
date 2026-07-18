"""Content-bound evidence contracts for scoped progress trust boundaries."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .consumer_receipt_contract import VALIDATOR_SIGNATURE_SHA256


OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,511}$")
GOAL_AXIS_RECEIPT_FIELDS = frozenset(
    {
        "contract_version",
        "receipt_id",
        "hook_id",
        "owner_id",
        "map_revision_id",
        "map_sha256",
        "adapter_revision_sha256",
        "consumer_id",
        "consumer_revision_sha256",
        "validator_signature_sha256",
        "hook_input_sha256",
        "hook_output_sha256",
        "invocation_status",
        "return_contract_status",
        "decision_consumption_status",
        "evidence_id",
        "evidence_sha256",
        "receipt_sha256",
    }
)
SELF_GROUNDED_CONTRACT_FIELDS = frozenset(
    {
        "contract_version",
        "owner_id",
        "contract_id",
        "predicate_id",
        "invariant_class",
        "adapter_revision_sha256",
        "evidence_id",
        "evidence_sha256",
        "receipt_sha256",
    }
)
PREMISE_REPLAY_FIELDS = frozenset(
    {
        "contract_version",
        "receipt_id",
        "contract_id",
        "predicate_id",
        "input_revision_id",
        "input_sha256",
        "replay_executor_id",
        "outcome",
        "calculation_input_sha256",
        "evidence_id",
        "evidence_sha256",
        "receipt_sha256",
    }
)
CALCULATION_FIELDS = frozenset(
    {
        "contract_version",
        "receipt_id",
        "contract_id",
        "calculation_id",
        "calculation_revision_id",
        "input_sha256",
        "output_sha256",
        "calculator_id",
        "outcome",
        "evidence_id",
        "evidence_sha256",
        "receipt_sha256",
    }
)
INDEPENDENT_OBSERVATION_FIELDS = frozenset(
    {
        "contract_version",
        "receipt_id",
        "subject_id",
        "observation_id",
        "producer_owner_id",
        "verifier_owner_id",
        "producer_invariant_id",
        "verifier_invariant_id",
        "producer_input_ids",
        "verification_input_ids",
        "source_overlap_status",
        "invariant_separation_status",
        "before_revision_id",
        "before_sha256",
        "after_revision_id",
        "after_sha256",
        "comparison_basis_id",
        "comparison_input_sha256",
        "observed_relation",
        "evidence_id",
        "evidence_sha256",
        "receipt_sha256",
    }
)


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _receipt_sha256(receipt: dict[str, Any]) -> str:
    return _canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )


def _full_sha256(value: Any) -> bool:
    normalized = str(value or "").strip().lower().removeprefix("sha256:")
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _opaque(value: Any) -> bool:
    return isinstance(value, str) and OPAQUE_ID.fullmatch(value.strip()) is not None


def canonical_goal_axis_receipt_sha256(receipt: dict[str, Any]) -> str:
    return _receipt_sha256(receipt)


def goal_axis_receipt_valid(
    receipt: Any,
    *,
    owner_id: str,
    map_revision_id: str,
    map_sha256: str,
    adapter_revision_sha256: str,
) -> bool:
    return bool(
        isinstance(receipt, dict)
        and set(receipt) == GOAL_AXIS_RECEIPT_FIELDS
        and receipt.get("contract_version") == 1
        and all(
            _opaque(receipt.get(field))
            for field in (
                "receipt_id",
                "owner_id",
                "map_revision_id",
                "consumer_id",
                "evidence_id",
            )
        )
        and all(
            _full_sha256(receipt.get(field))
            for field in (
                "map_sha256",
                "adapter_revision_sha256",
                "consumer_revision_sha256",
                "validator_signature_sha256",
                "hook_input_sha256",
                "hook_output_sha256",
                "evidence_sha256",
                "receipt_sha256",
            )
        )
        and receipt.get("hook_id") == "goal_axis_map"
        and receipt.get("owner_id") == owner_id
        and receipt.get("map_revision_id") == map_revision_id
        and receipt.get("map_sha256") == map_sha256
        and receipt.get("hook_output_sha256") == map_sha256
        and receipt.get("adapter_revision_sha256") == adapter_revision_sha256
        and receipt.get("validator_signature_sha256") == VALIDATOR_SIGNATURE_SHA256
        and receipt.get("invocation_status") == "completed"
        and receipt.get("return_contract_status") == "pass"
        and receipt.get("decision_consumption_status") == "consumed"
        and receipt.get("receipt_sha256") == _receipt_sha256(receipt)
    )


def canonical_self_grounded_receipt_sha256(receipt: dict[str, Any]) -> str:
    return _receipt_sha256(receipt)


def canonical_independent_observation_receipt_sha256(
    receipt: dict[str, Any],
) -> str:
    return _receipt_sha256(receipt)


def independent_observation_receipt_valid(
    receipt: Any,
    *,
    subject_id: str,
    observed_relation: str,
) -> bool:
    if not isinstance(receipt, dict) or set(receipt) != INDEPENDENT_OBSERVATION_FIELDS:
        return False
    producer_inputs = receipt.get("producer_input_ids")
    verifier_inputs = receipt.get("verification_input_ids")
    if (
        not isinstance(producer_inputs, list)
        or not producer_inputs
        or not isinstance(verifier_inputs, list)
        or not verifier_inputs
        or not all(_opaque(item) for item in [*producer_inputs, *verifier_inputs])
        or len(set(producer_inputs)) != len(producer_inputs)
        or len(set(verifier_inputs)) != len(verifier_inputs)
        or set(producer_inputs) & set(verifier_inputs)
    ):
        return False
    opaque_fields = (
        "receipt_id",
        "subject_id",
        "observation_id",
        "producer_owner_id",
        "verifier_owner_id",
        "producer_invariant_id",
        "verifier_invariant_id",
        "before_revision_id",
        "after_revision_id",
        "comparison_basis_id",
        "evidence_id",
    )
    sha_fields = (
        "before_sha256",
        "after_sha256",
        "comparison_input_sha256",
        "evidence_sha256",
        "receipt_sha256",
    )
    return bool(
        receipt.get("contract_version") == 1
        and all(_opaque(receipt.get(field)) for field in opaque_fields)
        and all(_full_sha256(receipt.get(field)) for field in sha_fields)
        and receipt.get("subject_id") == subject_id
        and receipt.get("observed_relation") == observed_relation
        and receipt.get("source_overlap_status") == "disjoint"
        and receipt.get("invariant_separation_status") == "independent"
        and receipt.get("producer_owner_id") != receipt.get("verifier_owner_id")
        and receipt.get("producer_invariant_id") != receipt.get("verifier_invariant_id")
        and receipt.get("before_revision_id") != receipt.get("after_revision_id")
        and receipt.get("before_sha256") != receipt.get("after_sha256")
        and receipt.get("receipt_sha256") == _receipt_sha256(receipt)
    )


def _closed_receipt(
    receipt: Any,
    fields: frozenset[str],
    opaque_fields: tuple[str, ...],
    sha_fields: tuple[str, ...],
) -> bool:
    return bool(
        isinstance(receipt, dict)
        and set(receipt) == fields
        and receipt.get("contract_version") == 1
        and all(_opaque(receipt.get(field)) for field in opaque_fields)
        and all(_full_sha256(receipt.get(field)) for field in sha_fields)
        and receipt.get("receipt_sha256") == _receipt_sha256(receipt)
    )


def self_grounded_evidence_valid(root_scope: dict[str, Any]) -> bool:
    contract = root_scope.get("self_grounded_contract_receipt")
    replay = root_scope.get("premise_replay_receipt")
    calculation = root_scope.get("calculation_receipt")
    if (
        not _closed_receipt(
            contract,
            SELF_GROUNDED_CONTRACT_FIELDS,
            ("owner_id", "contract_id", "predicate_id", "evidence_id"),
            ("adapter_revision_sha256", "evidence_sha256", "receipt_sha256"),
        )
        or not _closed_receipt(
            replay,
            PREMISE_REPLAY_FIELDS,
            (
                "receipt_id",
                "contract_id",
                "predicate_id",
                "input_revision_id",
                "replay_executor_id",
                "evidence_id",
            ),
            (
                "input_sha256",
                "calculation_input_sha256",
                "evidence_sha256",
                "receipt_sha256",
            ),
        )
        or not _closed_receipt(
            calculation,
            CALCULATION_FIELDS,
            (
                "receipt_id",
                "contract_id",
                "calculation_id",
                "calculation_revision_id",
                "calculator_id",
                "evidence_id",
            ),
            ("input_sha256", "output_sha256", "evidence_sha256", "receipt_sha256"),
        )
    ):
        return False
    return bool(
        contract.get("invariant_class") == "deterministic_self_grounded"
        and replay.get("outcome") == "pass"
        and calculation.get("outcome") == "pass"
        and contract.get("owner_id") == root_scope.get("self_grounded_owner_id")
        and contract.get("contract_id") == root_scope.get("self_grounded_contract_id")
        and replay.get("contract_id") == contract.get("contract_id")
        and replay.get("predicate_id") == contract.get("predicate_id")
        and calculation.get("contract_id") == contract.get("contract_id")
        and replay.get("calculation_input_sha256") == calculation.get("input_sha256")
        and root_scope.get("self_grounded_contract_receipt_sha256")
        == contract.get("receipt_sha256")
        and root_scope.get("premise_replay_receipt_sha256")
        == replay.get("receipt_sha256")
        and root_scope.get("calculation_receipt_sha256")
        == calculation.get("receipt_sha256")
    )


__all__ = (
    "canonical_goal_axis_receipt_sha256",
    "canonical_independent_observation_receipt_sha256",
    "canonical_self_grounded_receipt_sha256",
    "goal_axis_receipt_valid",
    "independent_observation_receipt_valid",
    "self_grounded_evidence_valid",
)
