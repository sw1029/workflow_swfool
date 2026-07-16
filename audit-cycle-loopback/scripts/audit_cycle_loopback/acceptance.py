from __future__ import annotations

from typing import Any
from . import values as _values
from . import vectors as _vectors


def infer_reachability_verdict(acceptance_min_output: Any, frozen_envelope: Any) -> str:
    minimums = _vectors.numeric_vector(acceptance_min_output)
    envelope = _vectors.numeric_vector(frozen_envelope)
    if not minimums or not envelope:
        return "indeterminate"
    comparable = False
    for key, minimum in minimums.items():
        candidates = (
            key,
            f"max_{key}",
            f"{key}_max",
            f"limit_{key}",
            f"{key}_limit",
            "max_output",
            "output_cap",
        )
        matching = [envelope[candidate] for candidate in candidates if candidate in envelope]
        if not matching:
            continue
        comparable = True
        if max(matching) < minimum:
            return "unreachable"
    return "reachable" if comparable else "indeterminate"

def normalize_gate_evaluation_status(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if text in {"pass", "passed", "ok", "valid", "verified", "satisfied", "complete", "true"}:
        return "pass"
    if text in {"fail", "failed", "block", "blocked", "invalid", "unverified", "unsatisfied", "false"}:
        return "fail"
    if text in {
        "not_evaluated",
        "not_eval",
        "not_provided",
        "missing",
        "unknown",
        "indeterminate",
        "not_applicable",
        "none",
        "null",
    }:
        return "not_evaluated"
    return None

def verifier_evaluation_status(value: dict[str, Any], verifier_contract: dict[str, Any], prefix: str) -> str | None:
    keys = (
        f"{prefix}_verifier_evaluation_status",
        f"{prefix}_verifier_status",
        "verifier_evaluation_status",
        "verifier_status",
        "live_verifier_status",
    )
    for key in keys:
        normalized = normalize_gate_evaluation_status(value.get(key))
        if normalized:
            return normalized
    for key in ("evaluation_status", "status", "verdict"):
        normalized = normalize_gate_evaluation_status(verifier_contract.get(key))
        if normalized:
            return normalized
    return None

def normalize_verifier_contract(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        source: Any = value
        for key in (
            "acceptance_verifier_contract",
            "metric_verifier_contract",
            "verifier_contract",
            "target_required_verifier",
            "required_verifier_contract",
        ):
            if key in value:
                source = value.get(key)
                break
        if isinstance(source, str):
            source = {"required_verifier": source}
        if not isinstance(source, dict):
            return {}
        contract = dict(source)
    elif isinstance(value, str) and value.strip():
        contract = {"required_verifier": value.strip()}
    else:
        return {}
    required_verifier = (
        contract.get("required_verifier")
        or contract.get("verifier_id")
        or contract.get("id")
        or contract.get("name")
    )
    if required_verifier and not contract.get("required_verifier"):
        contract["required_verifier"] = required_verifier
    if required_verifier and "verifier_required" not in contract and "required" not in contract:
        contract["verifier_required"] = True
    return contract

def acceptance_target_from_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    for key in (
        "target",
        "measurable_target",
        "acceptance_target",
        "original_target",
        "acceptance_min_output",
        "min_output",
        "minimum_output",
    ):
        if key in value and value.get(key) not in (None, "", []):
            return value.get(key)
    nested_gate = value.get("acceptance_reachability_gate")
    if isinstance(nested_gate, dict):
        return acceptance_target_from_value(nested_gate)
    return None

def merge_acceptance_verifier_contract(acceptance_value: Any, verifier_value: Any) -> Any:
    contract = normalize_verifier_contract(verifier_value)
    if not contract:
        return acceptance_value
    if isinstance(acceptance_value, dict):
        merged_value = dict(acceptance_value)
    else:
        merged_value = {}
    existing = merged_value.get("acceptance_verifier_contract") or merged_value.get("verifier_contract") or {}
    if not isinstance(existing, dict):
        existing = normalize_verifier_contract(existing)
    merged_value["acceptance_verifier_contract"] = {**contract, **existing}
    return merged_value

def acceptance_reachability_gate(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("acceptance_reachability_gate"), dict):
        value = value["acceptance_reachability_gate"]
    verifier_required = False
    required_verifier = None
    verifier_status: str | None = None
    if not isinstance(value, dict):
        verdict = "indeterminate"
        acceptance_min_output: Any = {}
        frozen_envelope: Any = {}
        residual_gap_policy: Any = None
        residual_gap_ratio: Any = None
        marginal_repair: bool = False
        envelope_thaw_item: Any = None
        thaw_condition: Any = None
        thaw_schedule: Any = None
    else:
        verifier_contract = (
            value.get("acceptance_verifier_contract")
            or value.get("verifier_contract")
            or value.get("required_verifier_contract")
            or {}
        )
        if not isinstance(verifier_contract, dict):
            verifier_contract = {}
        required_verifier = (
            value.get("required_verifier")
            or value.get("verifier_id")
            or verifier_contract.get("required_verifier")
            or verifier_contract.get("verifier_id")
        )
        verifier_required = _values.bool_value(
            value.get("verifier_required")
            or value.get("required_for_acceptance")
            or value.get("acceptance_verifier_required")
            or verifier_contract.get("required")
            or verifier_contract.get("verifier_required")
        ) or bool(str(required_verifier or "").strip())
        verifier_status = verifier_evaluation_status(value, verifier_contract, "acceptance")
        acceptance_min_output = (
            value.get("acceptance_min_output")
            or value.get("min_output")
            or value.get("minimum_output")
            or {}
        )
        frozen_envelope = value.get("frozen_envelope") or value.get("envelope") or value.get("bounds") or {}
        envelope_thaw_item = (
            value.get("envelope_thaw_item")
            or value.get("thaw_item")
            or value.get("thaw_plan_item")
        )
        thaw_condition = value.get("thaw_condition") or value.get("thaw_exit_condition")
        thaw_schedule = value.get("thaw_schedule") or value.get("envelope_ladder") or value.get("envelope_thaw_schedule")
        residual_gap_policy = value.get("residual_gap_policy")
        residual_gap_ratio = value.get("residual_gap_ratio") or value.get("gap_ratio")
        marginal_repair = _values.bool_value(value.get("marginal_repair") or value.get("marginal_repair_candidate"))
        verdict = str(
            value.get("reachability_verdict")
            or value.get("verdict")
            or value.get("status")
            or ""
        ).strip().lower()
        if _values.bool_value(value.get("acceptance_unreachable_under_frozen_config")):
            verdict = "unreachable"
        if verdict not in {"reachable", "unreachable", "indeterminate"}:
            verdict = infer_reachability_verdict(acceptance_min_output, frozen_envelope)
    unreachable = verdict == "unreachable"
    frozen_envelope_present = bool(frozen_envelope)
    thaw_item_present = bool(envelope_thaw_item or thaw_condition or thaw_schedule)
    envelope_thaw_item_required = unreachable and frozen_envelope_present and not thaw_item_present
    reachability_status = "fail" if unreachable else ("pass" if verdict == "reachable" else "not_evaluated")
    if verifier_required and verifier_status is None:
        verifier_status = "not_evaluated"
    verifier_failed = verifier_required and verifier_status == "fail"
    if unreachable or verifier_failed:
        evaluation_status = "fail"
    elif verifier_required and verifier_status != "pass":
        evaluation_status = "not_evaluated"
    else:
        evaluation_status = reachability_status
    acceptance_verifier_not_evaluated = verifier_required and verifier_status == "not_evaluated"
    unverifiable_acceptance_contract = verifier_required and acceptance_verifier_not_evaluated
    blocked = unreachable or verifier_failed or unverifiable_acceptance_contract or envelope_thaw_item_required
    return {
        "gate": "G-REACH",
        "acceptance_min_output": acceptance_min_output,
        "frozen_envelope": frozen_envelope,
        "reachability_verdict": verdict,
        "evaluation_status": evaluation_status,
        "required_verifier": required_verifier,
        "verifier_required": verifier_required,
        "acceptance_verifier_not_evaluated": acceptance_verifier_not_evaluated,
        "unverifiable_acceptance_contract": unverifiable_acceptance_contract,
        "residual_gap_policy": residual_gap_policy,
        "residual_gap_ratio": residual_gap_ratio,
        "marginal_repair": marginal_repair,
        "envelope_thaw_item": envelope_thaw_item,
        "thaw_condition": thaw_condition,
        "thaw_schedule": thaw_schedule,
        "envelope_thaw_item_present": thaw_item_present,
        "envelope_thaw_item_required": envelope_thaw_item_required,
        "acceptance_unreachable_under_frozen_config": unreachable,
        "relaxation_or_escalation_required": blocked,
        "status": "block" if blocked else verdict,
        "constrains_disposition": blocked,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": ["constraint_relaxation", "envelope_thaw_item", "verifier_contract_supply"],
        "blocked_micro_repair_under_frozen_envelope": blocked,
    }

def metric_validity_states(value: Any) -> list[str]:
    states: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key in ("metric_validity", "validity", "status", "verdict"):
                if item.get(key) is not None:
                    states.append(str(item.get(key)).strip().lower())
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return states

def oracle_metric_validity_gate(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("oracle_metric_validity_gate"), dict):
        value = value["oracle_metric_validity_gate"]
    states = metric_validity_states(value)
    tautological = any(state in {"tautological", "constant", "self_fulfilling", "self-fulfilling"} for state in states)
    provided = value is not None
    verifier_required = False
    required_verifier = None
    verifier_status: str | None = None
    if isinstance(value, dict):
        verifier_contract = (
            value.get("metric_verifier_contract")
            or value.get("verifier_contract")
            or value.get("required_verifier_contract")
            or {}
        )
        if not isinstance(verifier_contract, dict):
            verifier_contract = {}
        required_verifier = (
            value.get("required_verifier")
            or value.get("verifier_id")
            or verifier_contract.get("required_verifier")
            or verifier_contract.get("verifier_id")
        )
        verifier_required = _values.bool_value(
            value.get("verifier_required")
            or value.get("required_for_acceptance")
            or value.get("metric_verifier_required")
            or verifier_contract.get("required")
            or verifier_contract.get("verifier_required")
        ) or bool(str(required_verifier or "").strip())
        verifier_status = verifier_evaluation_status(value, verifier_contract, "metric")
    if verifier_required and verifier_status is None:
        verifier_status = "not_evaluated"
    verifier_failed = verifier_required and verifier_status == "fail"
    if tautological or verifier_failed:
        evaluation_status = "fail"
    elif verifier_required and verifier_status != "pass":
        evaluation_status = "not_evaluated"
    else:
        evaluation_status = "pass" if provided else "not_evaluated"
    metric_verifier_not_evaluated = verifier_required and verifier_status == "not_evaluated"
    required_not_evaluated = verifier_required and metric_verifier_not_evaluated
    return {
        "gate": "G-OENV",
        "metric_validity": "tautological" if tautological else ("checked" if provided else "unknown"),
        "metric_validity_states": states[:20],
        "metric_validity_self_check_provided": provided,
        "evaluation_status": evaluation_status,
        "required_verifier": required_verifier,
        "verifier_required": verifier_required,
        "metric_verifier_not_evaluated": metric_verifier_not_evaluated,
        "metric_goal_productive_excluded": tautological or verifier_failed or required_not_evaluated,
        "status": "block" if tautological or verifier_failed or required_not_evaluated else ("ok" if provided else "not_provided"),
        "constrains_disposition": tautological or verifier_failed or required_not_evaluated,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }
