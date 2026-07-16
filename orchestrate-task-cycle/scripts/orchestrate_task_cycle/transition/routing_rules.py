from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .access import first_value
from .constants import (
    CODE_WORKER_MODEL,
    MODEL_EFFORT_POLICY,
    MODEL_EFFORT_ROUTER,
    ROUTING_ENFORCEMENT_VALUES,
    SUPPORTED_AGENT_EFFORTS,
    SUPPORTED_AGENT_MODELS,
)
from .context import ValidationContext


FIELD_PATHS = {
    "requested_model": (
        "requested_model",
        "agent_routing.requested_model",
        "routing.requested_model",
        "routing.code_worker.requested_model",
        "worker.requested_model",
    ),
    "requested_model_ref": (
        "requested_model_ref",
        "agent_routing.requested_model_ref",
        "routing.requested_model_ref",
        "routing.code_worker.requested_model_ref",
        "worker.requested_model_ref",
    ),
    "model_configuration_status": (
        "model_configuration_status",
        "agent_routing.model_configuration_status",
        "routing.model_configuration_status",
        "routing.code_worker.model_configuration_status",
        "worker.model_configuration_status",
    ),
    "model_binding_receipt": (
        "model_binding_receipt",
        "agent_routing.model_binding_receipt",
        "routing.model_binding_receipt",
        "routing.code_worker.model_binding_receipt",
        "worker.model_binding_receipt",
    ),
    "policy_id": (
        "policy_id",
        "agent_routing.policy_id",
        "routing.policy_id",
        "routing.code_worker.policy_id",
        "worker.policy_id",
    ),
    "requested_effort": (
        "requested_reasoning_effort",
        "agent_routing.requested_reasoning_effort",
        "routing.requested_reasoning_effort",
        "routing.code_worker.requested_reasoning_effort",
        "worker.requested_reasoning_effort",
    ),
    "routing_tier": (
        "routing_tier",
        "agent_routing.routing_tier",
        "routing.routing_tier",
        "routing.code_worker.routing_tier",
        "worker.routing_tier",
    ),
    "routing_reason_codes": (
        "routing_reason_codes",
        "agent_routing.routing_reason_codes",
        "routing.routing_reason_codes",
        "routing.code_worker.routing_reason_codes",
        "worker.routing_reason_codes",
    ),
    "routing_signals": (
        "routing_signals",
        "agent_routing.routing_signals",
        "routing.routing_signals",
        "routing.code_worker.routing_signals",
        "worker.routing_signals",
    ),
    "routing_signal_evidence": (
        "routing_signal_evidence",
        "agent_routing.routing_signal_evidence",
        "routing.routing_signal_evidence",
        "routing.code_worker.routing_signal_evidence",
        "worker.routing_signal_evidence",
    ),
    "routing_violations": (
        "routing_violations",
        "agent_routing.routing_violations",
        "routing.routing_violations",
        "routing.code_worker.routing_violations",
        "worker.routing_violations",
    ),
    "final_direction_ownership": (
        "final_direction_ownership",
        "agent_routing.final_direction_ownership",
        "routing.final_direction_ownership",
        "worker.final_direction_ownership",
    ),
    "routing_enforcement": (
        "routing_enforcement",
        "agent_routing.routing_enforcement",
        "routing.routing_enforcement",
        "worker.routing_enforcement",
    ),
    "routing_applicability": (
        "agent_routing_applicability",
        "agent_routing.applicability",
        "routing.agent_routing_applicability",
    ),
    "actual_model": (
        "actual_model",
        "agent_routing.actual_model",
        "routing.actual_model",
        "worker.actual_model",
    ),
    "actual_effort": (
        "actual_reasoning_effort",
        "agent_routing.actual_reasoning_effort",
        "routing.actual_reasoning_effort",
        "worker.actual_reasoning_effort",
    ),
    "profile_id": (
        "profile_id",
        "agent_routing.profile_id",
        "routing.profile_id",
        "routing.code_worker.profile_id",
        "worker.profile_id",
    ),
}


@dataclass(frozen=True)
class RoutingEvidence:
    values: dict[str, Any]

    def get(self, field: str) -> Any:
        return self.values.get(field)

    @property
    def profile_id(self) -> str:
        return str(self.get("profile_id") or "")

    @property
    def applicability(self) -> str:
        return str(self.get("routing_applicability") or "").lower()

    def claim(self, state: ValidationContext) -> dict[str, Any]:
        source = state.routing_source
        return {
            "policy_id": self.get("policy_id"),
            "profile_id": self.profile_id,
            "routing_tier": self.get("routing_tier"),
            "requested_model_ref": self.get("requested_model_ref"),
            "requested_model": self.get("requested_model"),
            "model_configuration_status": self.get("model_configuration_status"),
            "model_binding_receipt": self.get("model_binding_receipt"),
            "requested_reasoning_effort": self.get("requested_effort"),
            "routing_reason_codes": self.get("routing_reason_codes"),
            "routing_signals": self.get("routing_signals") or {},
            "routing_signal_evidence": self.get("routing_signal_evidence") or {},
            "routing_violations": self.get("routing_violations") or [],
            "final_direction_ownership": self.get("final_direction_ownership"),
            "routing_enforcement": self.get("routing_enforcement"),
            "max_escalation_reason": first_value(
                source,
                "max_escalation_reason",
                "agent_routing.max_escalation_reason",
                "routing.max_escalation_reason",
            ),
            "prior_tier5_unresolved": first_value(
                source,
                "prior_tier5_unresolved",
                "agent_routing.prior_tier5_unresolved",
                "routing.prior_tier5_unresolved",
            ),
            "prior_tier5_evidence": first_value(
                source,
                "prior_tier5_evidence",
                "agent_routing.prior_tier5_evidence",
                "routing.prior_tier5_evidence",
            ),
            "agent_count": first_value(
                source,
                "agent_count",
                "agent_routing.agent_count",
                "routing.agent_count",
                "review_agent_count",
            ),
        }


def collect_routing_evidence(state: ValidationContext) -> RoutingEvidence:
    return RoutingEvidence(
        {
            field: first_value(state.routing_source, *paths)
            for field, paths in FIELD_PATHS.items()
        }
    )


def validate_routing_request(state: ValidationContext) -> None:
    evidence = collect_routing_evidence(state)
    worker_model = first_value(
        state.routing_source,
        "routing.code_worker_model",
        "worker.model",
        "code_worker_model",
    )
    if worker_model and str(worker_model) != CODE_WORKER_MODEL:
        state.add(
            "warn",
            "noncanonical_worker_model",
            f"Code-writing worker model must remain Tier 2/3 `{CODE_WORKER_MODEL}`.",
            {"worker_model": worker_model},
        )
    requested_model = evidence.get("requested_model")
    configuration = evidence.get("model_configuration_status")
    requested_effort = evidence.get("requested_effort")
    if (
        requested_model
        and str(configuration or "reference_only") == "reference_only"
        and str(requested_model) not in SUPPORTED_AGENT_MODELS
    ):
        state.add(
            "block",
            "unsupported_requested_model",
            "Delegated agent request is outside the tier routing policy.",
            {"requested_model": requested_model},
        )
    if requested_effort and str(requested_effort) not in SUPPORTED_AGENT_EFFORTS:
        state.add(
            "block",
            "unsupported_requested_effort",
            "Requested reasoning effort is outside the tier routing policy.",
            {"requested_reasoning_effort": requested_effort},
        )
    if _has_route_claim(evidence):
        _validate_route_claim(state, evidence)


def _has_route_claim(evidence: RoutingEvidence) -> bool:
    return any(
        (
            evidence.profile_id,
            evidence.get("routing_tier"),
            evidence.get("requested_model_ref"),
            evidence.get("requested_model"),
            evidence.get("model_configuration_status"),
            evidence.get("model_binding_receipt"),
            evidence.get("requested_effort"),
        )
    )


def _validate_route_claim(
    state: ValidationContext,
    evidence: RoutingEvidence,
) -> None:
    route_target = state.target_step
    supplied_target = str(first_value(state.routing_source, "target", "step") or "")
    if supplied_target and supplied_target != route_target:
        state.add(
            "block",
            "routing_target_transition_mismatch",
            "Caller-supplied routing target does not match the canonical transition target.",
            {
                "transition_target": route_target,
                "supplied_target": supplied_target,
            },
        )
    for finding in MODEL_EFFORT_ROUTER.validate_claim(
        evidence.claim(state), MODEL_EFFORT_POLICY, route_target
    ):
        state.add(
            "block",
            str(finding.get("code") or "model_effort_routing_invalid"),
            "Delegated model/effort claim violates the tier routing policy.",
            finding,
        )


def validate_routing_enforcement(state: ValidationContext) -> None:
    evidence = collect_routing_evidence(state)
    enforcement = evidence.get("routing_enforcement")
    if enforcement and str(enforcement) not in ROUTING_ENFORCEMENT_VALUES:
        state.add(
            "block",
            "invalid_routing_enforcement",
            "Agent routing enforcement has a noncanonical value.",
            {"routing_enforcement": enforcement},
        )
    if evidence.applicability == "delegated":
        _validate_delegated_evidence(state, evidence)
    actual_model = evidence.get("actual_model")
    actual_effort = evidence.get("actual_effort")
    if str(enforcement) == "enforced" and (not actual_model or not actual_effort):
        state.add(
            "block",
            "enforced_routing_actual_evidence_missing",
            "Enforced routing lacks actual model/effort runtime evidence.",
            {
                "actual_model": actual_model,
                "actual_reasoning_effort": actual_effort,
            },
        )
    if actual_effort and str(actual_effort) not in SUPPORTED_AGENT_EFFORTS:
        state.add(
            "block",
            "unsupported_actual_effort",
            "Actual reasoning effort is outside the tier routing policy.",
            {"actual_reasoning_effort": actual_effort},
        )
    _validate_actual_route(state, evidence)


def _validate_delegated_evidence(
    state: ValidationContext,
    evidence: RoutingEvidence,
) -> None:
    fields = (
        ("policy_id", evidence.get("policy_id")),
        ("profile_id", evidence.profile_id),
        ("routing_tier", evidence.get("routing_tier")),
        ("requested_model", evidence.get("requested_model")),
        ("requested_reasoning_effort", evidence.get("requested_effort")),
        ("routing_reason_codes", evidence.get("routing_reason_codes")),
        ("routing_enforcement", evidence.get("routing_enforcement")),
    )
    for field, value in fields:
        if value is None or str(value).strip() == "":
            state.add(
                "warn",
                "delegated_routing_evidence_missing",
                f"Delegated agent result is missing `{field}`.",
                {"field": field},
            )
    if evidence.get("routing_violations") is None:
        state.add(
            "warn",
            "delegated_routing_evidence_missing",
            "Delegated agent result is missing `routing_violations`.",
            {"field": "routing_violations"},
        )


def _validate_actual_route(
    state: ValidationContext,
    evidence: RoutingEvidence,
) -> None:
    actual_model = evidence.get("actual_model")
    actual_effort = evidence.get("actual_effort")
    requested_model = evidence.get("requested_model")
    requested_effort = evidence.get("requested_effort")
    if (
        str(evidence.get("model_configuration_status")) == "resolved"
        and actual_model
        and requested_model
        and str(actual_model) != str(requested_model)
    ):
        state.add(
            "block",
            "actual_model_route_mismatch",
            "Actual model does not match the validated requested route.",
            {"requested_model": requested_model, "actual_model": actual_model},
        )
    if (
        actual_effort
        and requested_effort
        and str(actual_effort) != str(requested_effort)
    ):
        state.add(
            "block",
            "actual_effort_route_mismatch",
            "Actual effort does not match the validated requested route.",
            {
                "requested_reasoning_effort": requested_effort,
                "actual_reasoning_effort": actual_effort,
            },
        )
