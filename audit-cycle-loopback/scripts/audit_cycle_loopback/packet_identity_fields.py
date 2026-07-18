from __future__ import annotations

from .runtime_dependencies import (
    Any,
    SCHEMA_VERSION,
    bool_value,
)

from .evaluation_frame import _require_values


def _identity_fields(state: dict[str, Any]) -> dict[str, Any]:
    (
        args,
        attempt_identity,
        attempt_revision_candidate,
        budget_evaluations,
        current_root_family_key,
        current_root_key,
        decision_artifact_ref,
        family_key,
        gate_compatibility_results,
        input_state_fingerprint,
        legacy_attempt_identity,
        legacy_family_key,
        provider_request_count,
        registry_label_correction,
        supersedes_attempt_identity_candidate,
        supersedes_attempt_revision_candidate,
    ) = _require_values(
        state,
        (
            "args",
            "attempt_identity",
            "attempt_revision_candidate",
            "budget_evaluations",
            "current_root_family_key",
            "current_root_key",
            "decision_artifact_ref",
            "family_key",
            "gate_compatibility_results",
            "input_state_fingerprint",
            "legacy_attempt_identity",
            "legacy_family_key",
            "provider_request_count",
            "registry_label_correction",
            "supersedes_attempt_identity_candidate",
            "supersedes_attempt_revision_candidate",
        ),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_contract_version": 1,
        "step": "loopback_audit",
        "cycle_id": args.cycle_id,
        "task_id": args.task_id,
        "family_key": family_key,
        "legacy_family_key": legacy_family_key,
        "root_key": current_root_key,
        "root_family_key": current_root_family_key,
        "artifact_family": args.artifact_family,
        "decision_artifact_ref": decision_artifact_ref,
        "artifact_id": decision_artifact_ref.get("artifact_id"),
        "artifact_class": decision_artifact_ref.get("artifact_class"),
        "artifact_sha256": decision_artifact_ref.get("artifact_sha256"),
        "production_lane_identity": decision_artifact_ref.get(
            "production_lane_identity"
        ),
        "discovery_basis": decision_artifact_ref.get("discovery_basis"),
        "scope_verified": bool_value(decision_artifact_ref.get("scope_verified")),
        "advisory_discovery": bool_value(
            decision_artifact_ref.get("advisory_discovery")
        ),
        "gate_compatibility_results": gate_compatibility_results,
        "required_gate_ids": sorted(
            {
                str(item.get("gate_id"))
                for item in gate_compatibility_results
                if item.get("gate_id")
            }
        ),
        "decision_consumed_gate_ids": sorted(
            {
                str(item.get("gate_id"))
                for item in gate_compatibility_results
                if item.get("gate_id")
                and item.get("gate_compatibility_status") == "compatible"
            }
        ),
        "decision_excluded_gate_ids": sorted(
            {
                str(item.get("gate_id"))
                for item in gate_compatibility_results
                if item.get("gate_id")
                and item.get("gate_compatibility_status") != "compatible"
            }
        ),
        "input_state_fingerprint": input_state_fingerprint,
        "attempt_identity": attempt_identity,
        "attempt_identity_version": 2,
        "legacy_attempt_identity": legacy_attempt_identity,
        "attempt_revision_candidate": attempt_revision_candidate,
        "supersedes_attempt_revision_candidate": supersedes_attempt_revision_candidate,
        "supersedes_attempt_identity_candidate": supersedes_attempt_identity_candidate,
        "registry_label_correction": registry_label_correction,
        "semantic_signature": args.semantic_signature,
        "provider_request_count": provider_request_count,
        "budget_evaluations": budget_evaluations,
        "budget_evaluation_status": (
            "budget_unverified"
            if any(
                contract.get("budget_evaluation_status") == "budget_unverified"
                for contract in budget_evaluations.values()
                if isinstance(contract, dict)
            )
            else "evaluated"
        ),
        "budget_unverified": sorted(
            budget_id
            for budget_id, contract in budget_evaluations.items()
            if isinstance(contract, dict)
            and contract.get("budget_evaluation_status") == "budget_unverified"
        ),
    }
