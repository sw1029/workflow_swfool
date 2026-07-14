#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


POLICY_PATH = Path(__file__).resolve().parents[1] / "references" / "model-effort-profiles.json"
MODEL_REF_PREFIX = "model_ref:"
EVIDENCE_ID_FIELDS = ("event_id", "run_id", "artifact_id", "ledger_event_id")


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    models = policy.get("models")
    tiers = policy.get("tiers")
    binding_contract = policy.get("model_binding_contract")
    if not isinstance(models, dict) or not models:
        raise ValueError("routing policy models must be a non-empty object")
    model_refs = {str(value) for value in models.values()}
    if any(not value.startswith(MODEL_REF_PREFIX) for value in model_refs):
        raise ValueError("global routing policy models must use abstract model_ref values")
    if not isinstance(tiers, dict) or not tiers:
        raise ValueError("routing policy tiers must be a non-empty object")
    for tier_id, tier in tiers.items():
        if not isinstance(tier, dict) or str(tier.get("model") or "") not in model_refs:
            raise ValueError(f"routing tier {tier_id} must reference policy models")
    if not isinstance(binding_contract, dict):
        raise ValueError("routing policy model_binding_contract is required")
    if binding_contract.get("request_field") != "model_bindings":
        raise ValueError("routing policy model binding request field is unsupported")
    max_policy = policy.get("max_escalation")
    if not isinstance(max_policy, dict) or str(max_policy.get("model") or "") not in model_refs:
        raise ValueError("max escalation must use a policy model_ref")
    return policy


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("routing policy must be a JSON object")
    return validate_policy(value)


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
    return any(evidence_present(value.get(field)) for field in EVIDENCE_ID_FIELDS)


def sanitized_evidence_reference(value: Any) -> Any:
    if isinstance(value, list):
        return [sanitized_evidence_reference(item) for item in value if valid_evidence_reference(item)]
    if not isinstance(value, dict):
        return None
    return {field: value[field] for field in EVIDENCE_ID_FIELDS if evidence_present(value.get(field))}


def sanitized_prior_tier5_evidence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    allowed = {
        *EVIDENCE_ID_FIELDS,
        "profile_id",
        "routing_tier",
        "requested_model_ref",
        "requested_model",
        "model_configuration_status",
        "requested_reasoning_effort",
        "unresolved_finding_id",
    }
    return {key: item for key, item in value.items() if key in allowed}


def receipt_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_model_binding(
    model_ref: str,
    request: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[str, str, dict[str, str] | None, list[dict[str, Any]]]:
    contract = policy["model_binding_contract"]
    raw_bindings = request.get(str(contract["request_field"]))
    if raw_bindings is None:
        return model_ref, "reference_only", None, []
    if not isinstance(raw_bindings, dict):
        return model_ref, "invalid", None, [{"code": "model_bindings_invalid"}]

    known_refs = {str(value) for value in policy["models"].values()}
    unknown_refs = sorted(str(key) for key in raw_bindings if str(key) not in known_refs)
    violations: list[dict[str, Any]] = []
    if unknown_refs:
        violations.append({"code": "unknown_model_binding_refs", "model_refs": unknown_refs})

    binding = raw_bindings.get(model_ref)
    if not isinstance(binding, dict):
        violations.append({"code": "model_binding_missing", "model_ref": model_ref})
        return model_ref, "invalid", None, violations

    model = binding.get("model")
    binding_id = binding.get("binding_id")
    source = binding.get("source")
    source_values = {str(item) for item in contract.get("binding_source_values", [])}
    if not isinstance(model, str) or not model.strip() or model.strip().startswith(MODEL_REF_PREFIX):
        violations.append({"code": "model_binding_model_invalid", "model_ref": model_ref})
    if not isinstance(binding_id, str) or not binding_id.strip():
        violations.append({"code": "model_binding_id_missing", "model_ref": model_ref})
    if str(source or "") not in source_values:
        violations.append(
            {
                "code": "model_binding_source_invalid",
                "model_ref": model_ref,
                "source": source,
            }
        )
    if violations:
        return model_ref, "invalid", None, violations
    receipt_body = {
        "model_ref": model_ref,
        "model_sha256": hashlib.sha256(model.strip().encode("utf-8")).hexdigest(),
        "binding_id": binding_id.strip(),
        "source": str(source),
    }
    receipt = {**receipt_body, "receipt_sha256": receipt_hash(receipt_body)}
    return model.strip(), "resolved", receipt, []


def valid_prior_tier5_evidence(value: Any, policy: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or not valid_evidence_reference(value):
        return False
    max_policy = policy["max_escalation"]
    return (
        str(value.get("profile_id") or "") == str(max_policy["required_evidence_profile"])
        and value.get("routing_tier") == int(max_policy["tier"])
        and str(value.get("requested_model_ref") or value.get("requested_model") or "") == str(max_policy["model"])
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
    signal_evidence = {
        str(key): sanitized_evidence_reference(value)
        for key, value in raw_signal_evidence.items()
        if str(key) in allowed_signals and valid_evidence_reference(value)
    }
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
        if signals.get(signal) and not valid_evidence_reference(raw_signal_evidence.get(signal)):
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
    model_ref = str(tier_spec["model"])
    effort = str(tier_spec["effort"])
    request_max = bool(request.get("request_max"))
    if request_max:
        max_policy = policy["max_escalation"]
        max_reason = str(request.get("max_escalation_reason") or "").strip()
        prior_tier5_evidence = sanitized_prior_tier5_evidence(
            request.get(str(max_policy["required_evidence_field"]))
        )
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
            model_ref = str(max_policy["model"])
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

    model, model_configuration_status, model_binding_receipt, binding_violations = resolve_model_binding(
        model_ref,
        request,
        policy,
    )
    violations.extend(binding_violations)

    result = {
        "policy_id": policy["policy_id"],
        "profile_id": profile_id,
        "routing_tier": tier,
        "requested_model_ref": model_ref,
        "requested_model": model,
        "model_configuration_status": model_configuration_status,
        "requested_reasoning_effort": effort,
        "routing_reason_codes": list(dict.fromkeys(reasons)),
        "routing_signals": {key: value for key, value in signals.items() if value},
        "routing_signal_evidence": {key: value for key, value in signal_evidence.items() if signals.get(key)},
        "dynamic_routing": bool(signal_request_present or request_max),
        "routing_violations": violations,
    }
    if model_binding_receipt is not None:
        result["model_binding_receipt"] = model_binding_receipt
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
    model_ref = str(claim.get("requested_model_ref") or "")
    effort = str(claim.get("requested_reasoning_effort") or "")
    expected_model_ref = str(tier_spec["model"])
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
        expected_model_ref = str(max_policy["model"])
        expected_effort = str(max_policy["effort"])

    configuration_status = str(claim.get("model_configuration_status") or "")
    binding_contract = policy["model_binding_contract"]
    allowed_statuses = {str(item) for item in binding_contract.get("configuration_status_values", [])}
    if not model_ref and model == expected_model_ref:
        model_ref = model
    if not configuration_status and model == expected_model_ref:
        configuration_status = "reference_only"
    if model_ref != expected_model_ref:
        findings.append(
            {
                "code": "tier_model_ref_mismatch",
                "routing_tier": tier,
                "expected_model_ref": expected_model_ref,
                "requested_model_ref": model_ref,
            }
        )
    if configuration_status not in allowed_statuses:
        findings.append(
            {
                "code": "model_configuration_status_invalid",
                "model_configuration_status": configuration_status or None,
            }
        )
    elif configuration_status == "reference_only":
        if model != expected_model_ref:
            findings.append(
                {
                    "code": "tier_model_mismatch",
                    "routing_tier": tier,
                    "expected_model": expected_model_ref,
                    "requested_model": model,
                }
            )
        if claim.get("routing_enforcement") == "enforced":
            findings.append({"code": "unresolved_model_binding_for_enforced_route", "model_ref": expected_model_ref})
    elif configuration_status == "resolved":
        receipt = claim.get("model_binding_receipt")
        if not isinstance(receipt, dict):
            findings.append({"code": "model_binding_receipt_missing", "model_ref": expected_model_ref})
        else:
            if str(receipt.get("model_ref") or "") != expected_model_ref:
                findings.append({"code": "model_binding_receipt_ref_mismatch", "model_ref": receipt.get("model_ref")})
            if not str(receipt.get("binding_id") or "").strip():
                findings.append({"code": "model_binding_id_missing", "model_ref": expected_model_ref})
            allowed_sources = {str(item) for item in binding_contract.get("binding_source_values", [])}
            if str(receipt.get("source") or "") not in allowed_sources:
                findings.append({"code": "model_binding_source_invalid", "source": receipt.get("source")})
            expected_model_sha256 = hashlib.sha256(model.encode("utf-8")).hexdigest()
            if str(receipt.get("model_sha256") or "") != expected_model_sha256:
                findings.append({"code": "model_binding_model_digest_mismatch", "model_ref": expected_model_ref})
            receipt_body = {
                "model_ref": receipt.get("model_ref"),
                "model_sha256": receipt.get("model_sha256"),
                "binding_id": receipt.get("binding_id"),
                "source": receipt.get("source"),
            }
            if str(receipt.get("receipt_sha256") or "") != receipt_hash(receipt_body):
                findings.append({"code": "model_binding_receipt_hash_mismatch", "model_ref": expected_model_ref})
        if not model or model.startswith(MODEL_REF_PREFIX):
            findings.append({"code": "resolved_model_binding_value_missing", "model_ref": expected_model_ref})
    elif configuration_status == "invalid":
        findings.append({"code": "model_binding_invalid", "model_ref": expected_model_ref})
    if effort != expected_effort:
        findings.append({"code": "tier_effort_mismatch", "routing_tier": tier, "expected_effort": expected_effort, "requested_reasoning_effort": effort})
    if effort in policy.get("prohibited_delegated_efforts", []):
        findings.append({"code": "delegated_ultra_prohibited"})
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select a governed configured model/effort tier for an orchestrated agent role.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--request", help="JSON object, JSON file, or '-' for stdin.")
    parser.add_argument("--model-bindings", help="Optional model-ref binding JSON object or file.")
    args = parser.parse_args(argv)
    try:
        request = load_json_arg(args.request)
        if args.model_bindings:
            request["model_bindings"] = load_json_arg(args.model_bindings)
        result = select_route(args.profile, request)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result["routing_violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
