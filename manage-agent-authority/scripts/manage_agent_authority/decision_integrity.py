"""Pure authority-decision projections shared by writers and validators."""

from __future__ import annotations

from typing import Any

from .canonical import object_sha256
from .contracts import risk_value


def _fingerprint_payload(
    request: dict[str, Any],
    context: dict[str, Any],
    manifest_binding: dict[str, str] | None,
    selected: list[dict[str, Any]],
    lineage: list[dict[str, Any]],
) -> dict[str, Any]:
    ceiling = context["session_ceiling"]
    envelope = context["goal_autonomy_envelope"]
    operation_key = ":".join(
        (
            request["skill_id"],
            request["skill_version"],
            request["operation_id"],
            request["operation_version"],
        )
    )
    high_risk = risk_value(request["risk_tier"]) >= risk_value("R2")
    design_decision = request["decision_class"] in {"D0", "D1"}
    return {
        "operation": {
            key: request[key]
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        },
        "subject": request["subject"],
        "capabilities": request["required_capabilities"],
        "manifest": manifest_binding,
        "session_projection": {
            "capabilities_permit": set(request["required_capabilities"]).issubset(
                ceiling["capabilities"]
            ),
            "risk_permits": risk_value(request["risk_tier"])
            <= risk_value(ceiling["risk_ceiling"]),
            "mutation_permits": request["mutation_class"]
            in ceiling["mutation_classes"],
        },
        "goal_projection": {
            "capabilities_permit": set(request["required_capabilities"]).issubset(
                envelope["capabilities"]
            ),
            "risk_permits": risk_value(request["risk_tier"])
            <= risk_value(envelope["risk_ceiling"]),
            "decision_permits": request["decision_class"]
            in envelope["decision_classes"],
            "subject_permits": request["subject"]["digest"] in envelope["subjects"],
            "operation_permits": operation_key in envelope["operations"],
        },
        "typed_decision_projection": {
            "external_input_status": request["context"]["external_input_status"],
            "external_input_evidence": request["context"]["external_input_evidence"],
            "risk_acceptance_status": request["context"]["risk_acceptance_status"]
            if high_risk
            else "not_applicable",
            "risk_acceptance_evidence": request["context"]["risk_acceptance_evidence"]
            if high_risk
            else None,
            "design_selection_status": request["context"]["design_selection_status"]
            if design_decision
            else "not_applicable",
            "design_selection_evidence": request["context"]["design_selection_evidence"]
            if design_decision
            else None,
        },
        "selected_grants": selected,
        "lineage_grants": lineage,
    }


def effective_authority_fingerprint(
    request: dict[str, Any],
    context: dict[str, Any],
    manifest_binding: dict[str, str] | None,
    selected: list[dict[str, Any]],
    lineage: list[dict[str, Any]],
) -> str:
    """Reproduce the evaluator fingerprint from already validated inputs."""

    return object_sha256(
        _fingerprint_payload(request, context, manifest_binding, selected, lineage)
    )


def stable_decision_projection(decision: dict[str, Any]) -> dict[str, Any]:
    """Return every canonical decision field except time-derived identity."""

    return {
        key: value
        for key, value in decision.items()
        if key not in {"decision_id", "evaluated_at"}
    }


__all__ = (
    "effective_authority_fingerprint",
    "stable_decision_projection",
)
