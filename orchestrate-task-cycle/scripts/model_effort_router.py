#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


POLICY_PATH = Path(__file__).resolve().parents[1] / "references" / "model-effort-profiles.json"


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_arg(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    stripped = value.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    path = Path(stripped)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(stripped)


def normalized_signals(value: Any, allowed: set[str]) -> tuple[dict[str, bool], list[str]]:
    if isinstance(value, list):
        raw = {str(item): True for item in value}
    elif isinstance(value, dict):
        raw = {str(key): bool(item) for key, item in value.items()}
    else:
        raw = {}
    unknown = sorted(key for key in raw if key not in allowed)
    return {key: raw.get(key, False) for key in allowed}, unknown


def evidence_present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return any(evidence_present(item) for item in value)
    if isinstance(value, dict):
        return any(evidence_present(item) for item in value.values())
    return value is not None and value is not False


def valid_evidence_reference(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value) and all(valid_evidence_reference(item) for item in value)
    if not isinstance(value, dict):
        return False
    locator_fields = ("path", "event_id", "run_id", "artifact_id", "ledger_event_id")
    return any(evidence_present(value.get(field)) for field in locator_fields)


def valid_prior_tier5_evidence(value: Any, policy: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or not valid_evidence_reference(value):
        return False
    max_policy = policy["max_escalation"]
    return (
        str(value.get("profile_id") or "") == str(max_policy["required_evidence_profile"])
        and value.get("routing_tier") == int(max_policy["tier"])
        and str(value.get("requested_model") or "") == str(max_policy["model"])
        and str(value.get("requested_reasoning_effort") or "") == str(policy["tiers"][str(max_policy["tier"])]["effort"])
        and evidence_present(value.get("unresolved_finding_id"))
    )


def rule_matches(rule: dict[str, Any], signals: dict[str, bool]) -> bool:
    when_all = [str(item) for item in rule.get("when_all", [])]
    when_any = [str(item) for item in rule.get("when_any", [])]
    return (not when_all or all(signals.get(item, False) for item in when_all)) and (
        not when_any or any(signals.get(item, False) for item in when_any)
    )


def select_route(
    profile_id: str,
    request: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policy or load_policy()
    request = request or {}
    profiles = policy.get("profiles", {})
    if profile_id not in profiles:
        raise ValueError(f"unknown routing profile: {profile_id}")

    profile = profiles[profile_id]
    allowed_signals = {str(item) for item in policy.get("dynamic_signals", [])}
    signals, unknown_signals = normalized_signals(request.get("signals"), allowed_signals)
    signal_request_present = any(signals.values())
    raw_signal_evidence = request.get("signal_evidence") if isinstance(request.get("signal_evidence"), dict) else {}
    signal_evidence = {str(key): value for key, value in raw_signal_evidence.items() if str(key) in allowed_signals}
    reasons = ["profile_default"]
    violations: list[dict[str, Any]] = []
    tier = int(profile["default_tier"])

    tier5_signals = {str(item) for item in policy.get("tier5_signal_evidence_required", [])}
    ownership_required = profile_id in {str(item) for item in policy.get("direction_ownership_profiles", [])}
    ownership = request.get("final_direction_ownership")
    if ownership_required and not isinstance(ownership, bool):
        violations.append({"code": "direction_ownership_unclassified", "profile_id": profile_id})
        for signal in tier5_signals:
            signals[signal] = False
    elif ownership_required and ownership is False:
        conflicting = sorted(signal for signal in tier5_signals if signals.get(signal))
        if conflicting:
            violations.append({"code": "direction_signal_conflicts_with_ownership", "signals": conflicting})
            for signal in conflicting:
                signals[signal] = False
    elif ownership_required and ownership is True and not any(signals.get(signal) for signal in tier5_signals):
        violations.append({"code": "direction_signal_missing_for_owned_decision", "profile_id": profile_id})

    for signal in policy.get("tier5_signal_evidence_required", []):
        signal = str(signal)
        if signals.get(signal) and not valid_evidence_reference(signal_evidence.get(signal)):
            violations.append({"code": "tier5_signal_evidence_missing", "signal": signal})
            signals[signal] = False

    if request.get("requested_tier") is not None:
        violations.append(
            {
                "code": "explicit_tier_override_prohibited",
                "value": request.get("requested_tier"),
            }
        )

    for rule in policy.get("promotion_rules", []):
        if not isinstance(rule, dict) or not rule_matches(rule, signals):
            continue
        minimum = int(rule.get("min_tier", tier))
        if minimum > tier:
            tier = minimum
        reasons.append(str(rule.get("rule_id") or "promotion_rule"))

    minimum = int(profile["min_tier"])
    maximum = int(profile["max_tier"])
    if tier < minimum:
        violations.append({"code": "tier_below_profile_min", "requested_tier": tier, "profile_min_tier": minimum})
        tier = minimum
        reasons.append("profile_min_clamp")
    if tier > maximum:
        violations.append({"code": "tier_above_profile_max", "requested_tier": tier, "profile_max_tier": maximum})
        tier = maximum
        reasons.append("profile_max_clamp")

    tier_spec = policy["tiers"][str(tier)]
    model = str(tier_spec["model"])
    effort = str(tier_spec["effort"])
    request_max = bool(request.get("request_max"))
    if request_max:
        max_policy = policy["max_escalation"]
        max_reason = str(request.get("max_escalation_reason") or "").strip()
        prior_tier5_evidence = request.get(str(max_policy["required_evidence_field"]))
        agent_count = request.get("agent_count")
        max_allowed = (
            bool(profile.get("allow_max"))
            and tier == int(max_policy["tier"])
            and signals.get(str(max_policy["required_signal"]), False)
            and valid_prior_tier5_evidence(prior_tier5_evidence, policy)
            and bool(max_reason)
            and agent_count == int(max_policy["required_agent_count"])
        )
        if max_allowed:
            model = str(max_policy["model"])
            effort = str(max_policy["effort"])
            reasons.append("bounded_max_escalation")
        else:
            violations.append(
                {
                    "code": "max_escalation_preconditions_unmet",
                    "allow_max": bool(profile.get("allow_max")),
                    "routing_tier": tier,
                    "prior_tier5_unresolved": signals.get(str(max_policy["required_signal"]), False),
                    "prior_tier5_evidence_valid": valid_prior_tier5_evidence(prior_tier5_evidence, policy),
                    "max_escalation_reason_present": bool(max_reason),
                    "agent_count": agent_count,
                }
            )

    if unknown_signals:
        violations.append({"code": "unknown_routing_signals", "signals": unknown_signals})

    result = {
        "policy_id": policy["policy_id"],
        "profile_id": profile_id,
        "routing_tier": tier,
        "requested_model": model,
        "requested_reasoning_effort": effort,
        "routing_reason_codes": list(dict.fromkeys(reasons)),
        "routing_signals": {key: value for key, value in signals.items() if value},
        "routing_signal_evidence": {key: value for key, value in signal_evidence.items() if signals.get(key)},
        "dynamic_routing": bool(signal_request_present or request_max),
        "routing_violations": violations,
    }
    if ownership_required:
        result["final_direction_ownership"] = ownership
    if request_max:
        result.update(
            {
                "prior_tier5_unresolved": bool(signals.get("prior_tier5_unresolved")),
                "prior_tier5_evidence": prior_tier5_evidence,
                "max_escalation_reason": max_reason,
                "agent_count": agent_count,
            }
        )
    return result


def validate_claim(
    claim: dict[str, Any],
    policy: dict[str, Any] | None = None,
    target: str | None = None,
) -> list[dict[str, Any]]:
    policy = policy or load_policy()
    findings: list[dict[str, Any]] = []
    profile_id = str(claim.get("profile_id") or "")
    profile = policy.get("profiles", {}).get(profile_id)
    if not isinstance(profile, dict):
        return [{"code": "unknown_model_effort_profile", "profile_id": profile_id}]
    allowed_profiles = policy.get("target_profiles", {}).get(str(target or ""))
    if isinstance(allowed_profiles, list) and profile_id not in {str(item) for item in allowed_profiles}:
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
        findings.append({"code": "reported_routing_violations", "routing_violations": claim.get("routing_violations")})

    try:
        tier = int(claim.get("routing_tier"))
    except (TypeError, ValueError):
        return [{"code": "routing_tier_missing_or_invalid", "routing_tier": claim.get("routing_tier")}]
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
    routing_signals, unknown_signals = normalized_signals(claim.get("routing_signals"), allowed_signals)
    routing_signal_evidence = claim.get("routing_signal_evidence") if isinstance(claim.get("routing_signal_evidence"), dict) else {}
    if unknown_signals:
        findings.append({"code": "unknown_routing_signals", "signals": unknown_signals})
    tier5_signals = {str(item) for item in policy.get("tier5_signal_evidence_required", [])}
    if profile_id in {str(item) for item in policy.get("direction_ownership_profiles", [])}:
        ownership = claim.get("final_direction_ownership")
        if not isinstance(ownership, bool):
            findings.append({"code": "direction_ownership_unclassified", "profile_id": profile_id})
        elif ownership is False and any(routing_signals.get(signal) for signal in tier5_signals):
            findings.append({"code": "direction_signal_conflicts_with_ownership"})
        elif ownership is True and not any(routing_signals.get(signal) for signal in tier5_signals):
            findings.append({"code": "direction_signal_missing_for_owned_decision", "profile_id": profile_id})
    for signal in sorted(tier5_signals):
        if routing_signals.get(signal) and not valid_evidence_reference(routing_signal_evidence.get(signal)):
            findings.append({"code": "tier5_signal_evidence_missing", "signal": signal})
    if tier != int(profile["default_tier"]):
        if not claim.get("routing_reason_codes"):
            findings.append({"code": "dynamic_tier_reason_missing", "routing_tier": tier})
        recomputed = select_route(
            profile_id,
            {
                "signals": routing_signals,
                "signal_evidence": routing_signal_evidence,
                "final_direction_ownership": claim.get("final_direction_ownership"),
            },
            policy,
        )
        if recomputed["routing_tier"] != tier or recomputed["routing_violations"]:
            findings.append(
                {
                    "code": "dynamic_tier_not_justified",
                    "routing_tier": tier,
                    "recomputed_tier": recomputed["routing_tier"],
                    "routing_signals": {key: value for key, value in routing_signals.items() if value},
                }
            )

    tier_spec = policy["tiers"][str(tier)]
    model = str(claim.get("requested_model") or "")
    effort = str(claim.get("requested_reasoning_effort") or "")
    expected_model = str(tier_spec["model"])
    expected_effort = str(tier_spec["effort"])
    if effort == str(policy["max_escalation"]["effort"]):
        max_policy = policy["max_escalation"]
        if not bool(profile.get("allow_max")) or tier != int(max_policy["tier"]):
            findings.append({"code": "max_not_allowed_for_profile_or_tier", "profile_id": profile_id, "routing_tier": tier})
        if (
            not claim.get("prior_tier5_unresolved")
            or not routing_signals.get(str(max_policy["required_signal"]), False)
            or not valid_prior_tier5_evidence(claim.get(str(max_policy["required_evidence_field"])), policy)
        ):
            findings.append({"code": "max_prior_tier5_evidence_missing"})
        if not str(claim.get("max_escalation_reason") or "").strip():
            findings.append({"code": "max_escalation_reason_missing"})
        if claim.get("agent_count") != int(max_policy["required_agent_count"]):
            findings.append({"code": "max_agent_count_invalid", "agent_count": claim.get("agent_count")})
        expected_model = str(max_policy["model"])
        expected_effort = str(max_policy["effort"])

    if model != expected_model:
        findings.append({"code": "tier_model_mismatch", "routing_tier": tier, "expected_model": expected_model, "requested_model": model})
    if effort != expected_effort:
        findings.append({"code": "tier_effort_mismatch", "routing_tier": tier, "expected_effort": expected_effort, "requested_reasoning_effort": effort})
    if effort in policy.get("prohibited_delegated_efforts", []):
        findings.append({"code": "delegated_ultra_prohibited"})
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select a governed GPT-5.6 model/effort tier for an orchestrated agent role.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--request", help="JSON object, JSON file, or '-' for stdin.")
    args = parser.parse_args(argv)
    try:
        result = select_route(args.profile, load_json_arg(args.request))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result["routing_violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
