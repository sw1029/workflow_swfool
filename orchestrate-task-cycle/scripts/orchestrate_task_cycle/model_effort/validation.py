from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .policy import (
    MODEL_REF_PREFIX,
    load_policy,
    normalized_signals,
    receipt_hash,
    valid_evidence_reference,
    valid_prior_tier5_evidence,
)
from .routing import select_route


@dataclass
class ClaimContext:
    claim: dict[str, Any]
    policy: dict[str, Any]
    target: str | None
    profile_id: str
    profile: dict[str, Any]
    tier: int
    routing_signals: dict[str, bool]
    routing_signal_evidence: dict[str, Any]
    findings: list[dict[str, Any]]


def _prepare_context(
    claim: dict[str, Any], policy: dict[str, Any], target: str | None
) -> ClaimContext | list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    profile_id = str(claim.get("profile_id") or "")
    profile = policy.get("profiles", {}).get(profile_id)
    if not isinstance(profile, dict):
        return [{"code": "unknown_model_effort_profile", "profile_id": profile_id}]
    allowed_profiles = policy.get("target_profiles", {}).get(str(target or ""))
    if isinstance(allowed_profiles, list) and profile_id not in {
        str(item) for item in allowed_profiles
    }:
        findings.append(
            {
                "code": "target_profile_mismatch",
                "target": target,
                "profile_id": profile_id,
                "allowed_profiles": allowed_profiles,
            }
        )
    if claim.get("policy_id") != policy.get("policy_id"):
        findings.append(
            {
                "code": "routing_policy_id_mismatch",
                "expected_policy_id": policy.get("policy_id"),
                "policy_id": claim.get("policy_id"),
            }
        )
    if claim.get("routing_violations"):
        findings.append(
            {
                "code": "reported_routing_violations",
                "routing_violations": claim.get("routing_violations"),
            }
        )
    try:
        tier = int(claim.get("routing_tier"))
    except (TypeError, ValueError):
        return [
            {
                "code": "routing_tier_missing_or_invalid",
                "routing_tier": claim.get("routing_tier"),
            }
        ]
    if str(tier) not in policy.get("tiers", {}):
        return [{"code": "unknown_routing_tier", "routing_tier": tier}]
    if tier < int(profile["min_tier"]) or tier > int(profile["max_tier"]):
        findings.append(
            {
                "code": "profile_tier_mismatch",
                "routing_tier": tier,
                "profile_min_tier": profile["min_tier"],
                "profile_max_tier": profile["max_tier"],
            }
        )
    allowed_signals = {str(item) for item in policy.get("dynamic_signals", [])}
    signals, unknown = normalized_signals(claim.get("routing_signals"), allowed_signals)
    evidence = (
        claim.get("routing_signal_evidence")
        if isinstance(claim.get("routing_signal_evidence"), dict)
        else {}
    )
    if unknown:
        findings.append({"code": "unknown_routing_signals", "signals": unknown})
    return ClaimContext(
        claim, policy, target, profile_id, profile, tier, signals, evidence, findings
    )


def _validate_signal_claims(ctx: ClaimContext) -> None:
    tier5_signals = {
        str(item) for item in ctx.policy.get("tier5_signal_evidence_required", [])
    }
    if ctx.profile_id in {
        str(item) for item in ctx.policy.get("direction_ownership_profiles", [])
    }:
        ownership = ctx.claim.get("final_direction_ownership")
        if not isinstance(ownership, bool):
            ctx.findings.append(
                {
                    "code": "direction_ownership_unclassified",
                    "profile_id": ctx.profile_id,
                }
            )
        elif ownership is False and any(
            ctx.routing_signals.get(signal) for signal in tier5_signals
        ):
            ctx.findings.append({"code": "direction_signal_conflicts_with_ownership"})
        elif ownership is True and not any(
            ctx.routing_signals.get(signal) for signal in tier5_signals
        ):
            ctx.findings.append(
                {
                    "code": "direction_signal_missing_for_owned_decision",
                    "profile_id": ctx.profile_id,
                }
            )
    for signal in sorted(tier5_signals):
        if ctx.routing_signals.get(signal) and not valid_evidence_reference(
            ctx.routing_signal_evidence.get(signal)
        ):
            ctx.findings.append(
                {"code": "tier5_signal_evidence_missing", "signal": signal}
            )
    if ctx.tier == int(ctx.profile["default_tier"]):
        return
    if not ctx.claim.get("routing_reason_codes"):
        ctx.findings.append(
            {"code": "dynamic_tier_reason_missing", "routing_tier": ctx.tier}
        )
    recomputed = select_route(
        ctx.profile_id,
        {
            "signals": ctx.routing_signals,
            "signal_evidence": ctx.routing_signal_evidence,
            "final_direction_ownership": ctx.claim.get("final_direction_ownership"),
        },
        ctx.policy,
    )
    if recomputed["routing_tier"] != ctx.tier or recomputed["routing_violations"]:
        ctx.findings.append(
            {
                "code": "dynamic_tier_not_justified",
                "routing_tier": ctx.tier,
                "recomputed_tier": recomputed["routing_tier"],
                "routing_signals": {
                    key: value for key, value in ctx.routing_signals.items() if value
                },
            }
        )


def _expected_route(ctx: ClaimContext) -> tuple[str, str, str, str, str]:
    tier_spec = ctx.policy["tiers"][str(ctx.tier)]
    model = str(ctx.claim.get("requested_model") or "")
    model_ref = str(ctx.claim.get("requested_model_ref") or "")
    effort = str(ctx.claim.get("requested_reasoning_effort") or "")
    expected_model_ref = str(tier_spec["model"])
    expected_effort = str(tier_spec["effort"])
    if effort == str(ctx.policy["max_escalation"]["effort"]):
        max_policy = ctx.policy["max_escalation"]
        if not bool(ctx.profile.get("allow_max")) or ctx.tier != int(
            max_policy["tier"]
        ):
            ctx.findings.append(
                {
                    "code": "max_not_allowed_for_profile_or_tier",
                    "profile_id": ctx.profile_id,
                    "routing_tier": ctx.tier,
                }
            )
        if (
            not ctx.claim.get("prior_tier5_unresolved")
            or not ctx.routing_signals.get(str(max_policy["required_signal"]), False)
            or not valid_prior_tier5_evidence(
                ctx.claim.get(str(max_policy["required_evidence_field"])), ctx.policy
            )
        ):
            ctx.findings.append({"code": "max_prior_tier5_evidence_missing"})
        if not str(ctx.claim.get("max_escalation_reason") or "").strip():
            ctx.findings.append({"code": "max_escalation_reason_missing"})
        if ctx.claim.get("agent_count") != int(max_policy["required_agent_count"]):
            ctx.findings.append(
                {
                    "code": "max_agent_count_invalid",
                    "agent_count": ctx.claim.get("agent_count"),
                }
            )
        expected_model_ref = str(max_policy["model"])
        expected_effort = str(max_policy["effort"])
    return model, model_ref, effort, expected_model_ref, expected_effort


def _validate_resolved_binding(
    ctx: ClaimContext, model: str, expected_model_ref: str
) -> None:
    receipt = ctx.claim.get("model_binding_receipt")
    if not isinstance(receipt, dict):
        ctx.findings.append(
            {"code": "model_binding_receipt_missing", "model_ref": expected_model_ref}
        )
    else:
        if str(receipt.get("model_ref") or "") != expected_model_ref:
            ctx.findings.append(
                {
                    "code": "model_binding_receipt_ref_mismatch",
                    "model_ref": receipt.get("model_ref"),
                }
            )
        if not str(receipt.get("binding_id") or "").strip():
            ctx.findings.append(
                {"code": "model_binding_id_missing", "model_ref": expected_model_ref}
            )
        allowed_sources = {
            str(item)
            for item in ctx.policy["model_binding_contract"].get(
                "binding_source_values", []
            )
        }
        if str(receipt.get("source") or "") not in allowed_sources:
            ctx.findings.append(
                {
                    "code": "model_binding_source_invalid",
                    "source": receipt.get("source"),
                }
            )
        expected_digest = hashlib.sha256(model.encode("utf-8")).hexdigest()
        if str(receipt.get("model_sha256") or "") != expected_digest:
            ctx.findings.append(
                {
                    "code": "model_binding_model_digest_mismatch",
                    "model_ref": expected_model_ref,
                }
            )
        body = {
            "model_ref": receipt.get("model_ref"),
            "model_sha256": receipt.get("model_sha256"),
            "binding_id": receipt.get("binding_id"),
            "source": receipt.get("source"),
        }
        if str(receipt.get("receipt_sha256") or "") != receipt_hash(body):
            ctx.findings.append(
                {
                    "code": "model_binding_receipt_hash_mismatch",
                    "model_ref": expected_model_ref,
                }
            )
    if not model or model.startswith(MODEL_REF_PREFIX):
        ctx.findings.append(
            {
                "code": "resolved_model_binding_value_missing",
                "model_ref": expected_model_ref,
            }
        )


def _validate_model_claim(ctx: ClaimContext) -> None:
    model, model_ref, effort, expected_model_ref, expected_effort = _expected_route(ctx)
    status = str(ctx.claim.get("model_configuration_status") or "")
    allowed_statuses = {
        str(item)
        for item in ctx.policy["model_binding_contract"].get(
            "configuration_status_values", []
        )
    }
    if not model_ref and model == expected_model_ref:
        model_ref = model
    if not status and model == expected_model_ref:
        status = "reference_only"
    if model_ref != expected_model_ref:
        ctx.findings.append(
            {
                "code": "tier_model_ref_mismatch",
                "routing_tier": ctx.tier,
                "expected_model_ref": expected_model_ref,
                "requested_model_ref": model_ref,
            }
        )
    if status not in allowed_statuses:
        ctx.findings.append(
            {
                "code": "model_configuration_status_invalid",
                "model_configuration_status": status or None,
            }
        )
    elif status == "reference_only":
        if model != expected_model_ref:
            ctx.findings.append(
                {
                    "code": "tier_model_mismatch",
                    "routing_tier": ctx.tier,
                    "expected_model": expected_model_ref,
                    "requested_model": model,
                }
            )
        if ctx.claim.get("routing_enforcement") == "enforced":
            ctx.findings.append(
                {
                    "code": "unresolved_model_binding_for_enforced_route",
                    "model_ref": expected_model_ref,
                }
            )
    elif status == "resolved":
        _validate_resolved_binding(ctx, model, expected_model_ref)
    elif status == "invalid":
        ctx.findings.append(
            {"code": "model_binding_invalid", "model_ref": expected_model_ref}
        )
    if effort != expected_effort:
        ctx.findings.append(
            {
                "code": "tier_effort_mismatch",
                "routing_tier": ctx.tier,
                "expected_effort": expected_effort,
                "requested_reasoning_effort": effort,
            }
        )
    if effort in ctx.policy.get("prohibited_delegated_efforts", []):
        ctx.findings.append({"code": "delegated_ultra_prohibited"})


def validate_claim(
    claim: dict[str, Any],
    policy: dict[str, Any] | None = None,
    target: str | None = None,
) -> list[dict[str, Any]]:
    prepared = _prepare_context(claim, policy or load_policy(), target)
    if isinstance(prepared, list):
        return prepared
    _validate_signal_claims(prepared)
    _validate_model_claim(prepared)
    return prepared.findings
