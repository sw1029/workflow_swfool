from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .policy import (
    load_policy,
    normalized_signals,
    resolve_model_binding,
    rule_matches,
    sanitized_evidence_reference,
    sanitized_prior_tier5_evidence,
    valid_evidence_reference,
    valid_prior_tier5_evidence,
)


@dataclass
class RouteState:
    profile_id: str
    request: dict[str, Any]
    policy: dict[str, Any]
    profile: dict[str, Any]
    signals: dict[str, bool]
    unknown_signals: list[str]
    signal_request_present: bool
    raw_signal_evidence: dict[str, Any]
    signal_evidence: dict[str, Any]
    reasons: list[str] = field(default_factory=lambda: ["profile_default"])
    violations: list[dict[str, Any]] = field(default_factory=list)
    tier: int = 0
    ownership_required: bool = False
    ownership: Any = None
    request_max: bool = False
    max_reason: str = ""
    prior_tier5_evidence: dict[str, Any] | None = None
    agent_count: Any = None


def _prepare_state(
    profile_id: str, request: dict[str, Any], policy: dict[str, Any]
) -> RouteState:
    profiles = policy.get("profiles", {})
    if profile_id not in profiles:
        raise ValueError(f"unknown routing profile: {profile_id}")
    profile = profiles[profile_id]
    allowed_signals = {str(item) for item in policy.get("dynamic_signals", [])}
    signals, unknown_signals = normalized_signals(
        request.get("signals"), allowed_signals
    )
    raw_evidence = (
        request.get("signal_evidence")
        if isinstance(request.get("signal_evidence"), dict)
        else {}
    )
    evidence = {
        str(key): sanitized_evidence_reference(value)
        for key, value in raw_evidence.items()
        if str(key) in allowed_signals and valid_evidence_reference(value)
    }
    return RouteState(
        profile_id=profile_id,
        request=request,
        policy=policy,
        profile=profile,
        signals=signals,
        unknown_signals=unknown_signals,
        signal_request_present=any(signals.values()),
        raw_signal_evidence=raw_evidence,
        signal_evidence=evidence,
        tier=int(profile["default_tier"]),
    )


def _apply_signal_policy(state: RouteState) -> None:
    tier5_signals = {
        str(item) for item in state.policy.get("tier5_signal_evidence_required", [])
    }
    state.ownership_required = state.profile_id in {
        str(item) for item in state.policy.get("direction_ownership_profiles", [])
    }
    state.ownership = state.request.get("final_direction_ownership")
    if state.ownership_required and not isinstance(state.ownership, bool):
        state.violations.append(
            {"code": "direction_ownership_unclassified", "profile_id": state.profile_id}
        )
        for signal in tier5_signals:
            state.signals[signal] = False
    elif state.ownership_required and state.ownership is False:
        conflicting = sorted(
            signal for signal in tier5_signals if state.signals.get(signal)
        )
        if conflicting:
            state.violations.append(
                {
                    "code": "direction_signal_conflicts_with_ownership",
                    "signals": conflicting,
                }
            )
            for signal in conflicting:
                state.signals[signal] = False
    elif (
        state.ownership_required
        and state.ownership is True
        and not any(state.signals.get(signal) for signal in tier5_signals)
    ):
        state.violations.append(
            {
                "code": "direction_signal_missing_for_owned_decision",
                "profile_id": state.profile_id,
            }
        )

    for raw_signal in state.policy.get("tier5_signal_evidence_required", []):
        signal = str(raw_signal)
        if state.signals.get(signal) and not valid_evidence_reference(
            state.raw_signal_evidence.get(signal)
        ):
            state.violations.append(
                {"code": "tier5_signal_evidence_missing", "signal": signal}
            )
            state.signals[signal] = False


def _select_tier(state: RouteState) -> None:
    if state.request.get("requested_tier") is not None:
        state.violations.append(
            {
                "code": "explicit_tier_override_prohibited",
                "value": state.request.get("requested_tier"),
            }
        )
    for rule in state.policy.get("promotion_rules", []):
        if not isinstance(rule, dict) or not rule_matches(rule, state.signals):
            continue
        minimum = int(rule.get("min_tier", state.tier))
        if minimum > state.tier:
            state.tier = minimum
        state.reasons.append(str(rule.get("rule_id") or "promotion_rule"))
    minimum = int(state.profile["min_tier"])
    maximum = int(state.profile["max_tier"])
    if state.tier < minimum:
        state.violations.append(
            {
                "code": "tier_below_profile_min",
                "requested_tier": state.tier,
                "profile_min_tier": minimum,
            }
        )
        state.tier = minimum
        state.reasons.append("profile_min_clamp")
    if state.tier > maximum:
        state.violations.append(
            {
                "code": "tier_above_profile_max",
                "requested_tier": state.tier,
                "profile_max_tier": maximum,
            }
        )
        state.tier = maximum
        state.reasons.append("profile_max_clamp")


def _apply_max_escalation(
    state: RouteState, model_ref: str, effort: str
) -> tuple[str, str]:
    state.request_max = bool(state.request.get("request_max"))
    if not state.request_max:
        return model_ref, effort
    max_policy = state.policy["max_escalation"]
    state.max_reason = str(state.request.get("max_escalation_reason") or "").strip()
    state.prior_tier5_evidence = sanitized_prior_tier5_evidence(
        state.request.get(str(max_policy["required_evidence_field"]))
    )
    state.agent_count = state.request.get("agent_count")
    max_allowed = (
        bool(state.profile.get("allow_max"))
        and state.tier == int(max_policy["tier"])
        and state.signals.get(str(max_policy["required_signal"]), False)
        and valid_prior_tier5_evidence(state.prior_tier5_evidence, state.policy)
        and bool(state.max_reason)
        and state.agent_count == int(max_policy["required_agent_count"])
    )
    if max_allowed:
        state.reasons.append("bounded_max_escalation")
        return str(max_policy["model"]), str(max_policy["effort"])
    state.violations.append(
        {
            "code": "max_escalation_preconditions_unmet",
            "allow_max": bool(state.profile.get("allow_max")),
            "routing_tier": state.tier,
            "prior_tier5_unresolved": state.signals.get(
                str(max_policy["required_signal"]), False
            ),
            "prior_tier5_evidence_valid": valid_prior_tier5_evidence(
                state.prior_tier5_evidence, state.policy
            ),
            "max_escalation_reason_present": bool(state.max_reason),
            "agent_count": state.agent_count,
        }
    )
    return model_ref, effort


def _result(state: RouteState, model_ref: str, effort: str) -> dict[str, Any]:
    if state.unknown_signals:
        state.violations.append(
            {"code": "unknown_routing_signals", "signals": state.unknown_signals}
        )
    model, status, receipt, binding_violations = resolve_model_binding(
        model_ref, state.request, state.policy
    )
    state.violations.extend(binding_violations)
    result = {
        "policy_id": state.policy["policy_id"],
        "profile_id": state.profile_id,
        "routing_tier": state.tier,
        "requested_model_ref": model_ref,
        "requested_model": model,
        "model_configuration_status": status,
        "requested_reasoning_effort": effort,
        "routing_reason_codes": list(dict.fromkeys(state.reasons)),
        "routing_signals": {
            key: value for key, value in state.signals.items() if value
        },
        "routing_signal_evidence": {
            key: value
            for key, value in state.signal_evidence.items()
            if state.signals.get(key)
        },
        "dynamic_routing": bool(state.signal_request_present or state.request_max),
        "routing_violations": state.violations,
    }
    if receipt is not None:
        result["model_binding_receipt"] = receipt
    if state.ownership_required:
        result["final_direction_ownership"] = state.ownership
    if state.request_max:
        result.update(
            {
                "prior_tier5_unresolved": bool(
                    state.signals.get("prior_tier5_unresolved")
                ),
                "prior_tier5_evidence": state.prior_tier5_evidence,
                "max_escalation_reason": state.max_reason,
                "agent_count": state.agent_count,
            }
        )
    return result


def select_route(
    profile_id: str,
    request: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_policy = policy or load_policy()
    state = _prepare_state(profile_id, request or {}, resolved_policy)
    _apply_signal_policy(state)
    _select_tier(state)
    tier_spec = resolved_policy["tiers"][str(state.tier)]
    model_ref, effort = _apply_max_escalation(
        state, str(tier_spec["model"]), str(tier_spec["effort"])
    )
    return _result(state, model_ref, effort)
