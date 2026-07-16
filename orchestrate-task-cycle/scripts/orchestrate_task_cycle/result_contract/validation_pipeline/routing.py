from __future__ import annotations

from .shared import (
    AGENT_ROUTING_TARGETS,
    MODEL_EFFORT_POLICY,
    MODEL_EFFORT_ROUTER,
    ROUTING_ENFORCEMENT_VALUES,
    SUPPORTED_AGENT_EFFORTS,
    SUPPORTED_AGENT_MODELS,
    add,
    has_value,
    value_for,
)
from .state import ValidationState


def check_routing(state: ValidationState) -> None:
    target = state.target
    result = state.result
    findings = state.findings
    severity = state.severity
    if target in AGENT_ROUTING_TARGETS:
        applicability = str(value_for(result, "agent_routing_applicability") or "").lower()
        if applicability not in {"delegated", "deterministic_only", "delegation_unavailable"}:
            add(
                findings,
                severity,
                "agent_routing_applicability_missing",
                "Agent-bearing phase must declare whether work was delegated, deterministic-only, or unavailable.",
            )
        elif applicability == "delegated":
            for field in ("policy_id", "profile_id", "routing_tier", "requested_model", "requested_reasoning_effort", "routing_reason_codes", "routing_enforcement"):
                if not has_value(result, field):
                    add(findings, severity, "delegated_routing_evidence_missing", f"Delegated result is missing `{field}`.", {"field": field})
            if value_for(result, "routing_violations") is None:
                add(findings, severity, "delegated_routing_evidence_missing", "Delegated result is missing `routing_violations`.", {"field": "routing_violations"})
            requested_model = str(value_for(result, "requested_model") or "")
            requested_model_ref = str(value_for(result, "requested_model_ref") or "")
            model_configuration_status = str(value_for(result, "model_configuration_status") or "")
            model_binding_receipt = value_for(result, "model_binding_receipt")
            requested_effort = str(value_for(result, "requested_reasoning_effort") or "")
            enforcement = str(value_for(result, "routing_enforcement") or "")
            claim = {
                "policy_id": value_for(result, "policy_id"),
                "profile_id": value_for(result, "profile_id"),
                "routing_tier": value_for(result, "routing_tier"),
                "requested_model_ref": requested_model_ref,
                "requested_model": requested_model,
                "model_configuration_status": model_configuration_status,
                "model_binding_receipt": model_binding_receipt,
                "requested_reasoning_effort": requested_effort,
                "routing_reason_codes": value_for(result, "routing_reason_codes"),
                "routing_signals": value_for(result, "routing_signals") or {},
                "routing_signal_evidence": value_for(result, "routing_signal_evidence") or {},
                "routing_violations": value_for(result, "routing_violations") or [],
                "final_direction_ownership": value_for(result, "final_direction_ownership"),
                "routing_enforcement": enforcement,
                "max_escalation_reason": value_for(result, "max_escalation_reason"),
                "prior_tier5_unresolved": value_for(result, "prior_tier5_unresolved"),
                "prior_tier5_evidence": value_for(result, "prior_tier5_evidence"),
                "agent_count": value_for(result, "agent_count"),
            }
            for routing_finding in MODEL_EFFORT_ROUTER.validate_claim(claim, MODEL_EFFORT_POLICY, target):
                code = str(routing_finding.get("code") or "model_effort_routing_invalid")
                add(
                    findings,
                    "block",
                    code,
                    "Delegated model/effort claim violates the tier routing policy.",
                    routing_finding,
                )
            if (
                requested_model
                and (model_configuration_status or "reference_only") == "reference_only"
                and requested_model not in SUPPORTED_AGENT_MODELS
            ):
                add(findings, "block", "unsupported_requested_model", "Requested model is outside the tier routing policy.", {"requested_model": requested_model})
            if requested_effort and requested_effort not in SUPPORTED_AGENT_EFFORTS:
                add(findings, "block", "unsupported_requested_effort", "Requested effort is outside the tier routing policy.", {"requested_reasoning_effort": requested_effort})
            if enforcement and enforcement not in ROUTING_ENFORCEMENT_VALUES:
                add(findings, "block", "invalid_routing_enforcement", "Delegated result has invalid routing enforcement.", {"routing_enforcement": enforcement})
            if enforcement == "enforced" and (not has_value(result, "actual_model") or not has_value(result, "actual_reasoning_effort")):
                add(findings, "block", "enforced_routing_actual_evidence_missing", "Enforced routing requires actual model and effort evidence.")
            if enforcement in {"prompt_only", "inherited_unverified"} and not has_value(result, "routing_limitation"):
                add(findings, severity, "routing_limitation_missing", "Non-enforced routing requires a concrete limitation note.")
            actual_model = str(value_for(result, "actual_model") or "")
            actual_effort = str(value_for(result, "actual_reasoning_effort") or "")
            if actual_effort and actual_effort not in SUPPORTED_AGENT_EFFORTS:
                add(findings, "block", "unsupported_actual_effort", "Actual effort is outside the tier routing policy.", {"actual_reasoning_effort": actual_effort})
            if model_configuration_status == "resolved" and actual_model and requested_model and actual_model != requested_model:
                add(findings, "block", "actual_model_route_mismatch", "Actual model does not match the validated requested route.", {"requested_model": requested_model, "actual_model": actual_model})
            if actual_effort and requested_effort and actual_effort != requested_effort:
                add(findings, "block", "actual_effort_route_mismatch", "Actual effort does not match the validated requested route.", {"requested_reasoning_effort": requested_effort, "actual_reasoning_effort": actual_effort})
        elif applicability == "delegation_unavailable" and not has_value(result, "routing_limitation"):
            add(findings, severity, "routing_limitation_missing", "Unavailable delegation requires a concrete routing limitation.")
    
