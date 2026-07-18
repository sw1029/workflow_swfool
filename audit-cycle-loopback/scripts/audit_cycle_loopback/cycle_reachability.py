"""Pure, fail-quiet cycle-scale reachability calculation.

The repository adapter owns scale meanings and throughput measurement.  This
module only normalizes their scalar contract, checks comparability, and performs
the bounded capacity calculation needed by the generic workflow.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _nonnegative_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    return next(
        (mapping[key] for key in keys if mapping.get(key) not in (None, "")), None
    )


def _content_id(prefix: str, supplied: object, body: dict[str, Any]) -> str:
    return _text(supplied) or f"{prefix}-{_canonical_sha256(body)[:24]}"


def _normalize_scale(value: object) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(value, dict):
        return {}, ["acceptance_scale_missing"]
    required = _positive_number(
        _first(
            value, "required_scale", "scale", "value", "minimum_scale", "target_scale"
        )
    )
    unit = _text(_first(value, "scale_unit", "unit", "throughput_unit"))
    errors: list[str] = []
    if required is None:
        errors.append("required_scale_missing_or_invalid")
    if unit is None:
        errors.append("acceptance_scale_unit_missing")
    body = {"required_scale": required, "scale_unit": unit}
    if errors:
        return body, errors
    body["acceptance_scale_id"] = _content_id(
        "acceptance-scale",
        _first(value, "acceptance_scale_id", "scale_id", "evidence_id"),
        body,
    )
    return body, []


def _normalize_throughput(value: object) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(value, dict):
        return {}, ["throughput_evidence_missing"]
    observed = _positive_number(
        _first(value, "observed_cycle_throughput", "throughput", "value", "per_cycle")
    )
    unit = _text(_first(value, "throughput_unit", "unit", "scale_unit"))
    cap = _positive_number(
        _first(
            value,
            "cycle_execution_cap",
            "cycle_cap",
            "max_cycles",
            "execution_cycle_cap",
        )
    )
    lower = _nonnegative_number(
        _first(value, "confidence_lower_bound", "throughput_lower_bound", "lower_bound")
    )
    upper = _nonnegative_number(
        _first(value, "confidence_upper_bound", "throughput_upper_bound", "upper_bound")
    )
    errors: list[str] = []
    if observed is None:
        errors.append("observed_cycle_throughput_missing_or_invalid")
    if unit is None:
        errors.append("throughput_unit_missing")
    if cap is None:
        errors.append("cycle_execution_cap_missing_or_invalid")
    if lower is not None and upper is not None and lower > upper:
        errors.append("throughput_confidence_interval_invalid")
    if observed is not None and lower is not None and observed < lower:
        errors.append("throughput_below_confidence_lower_bound")
    if observed is not None and upper is not None and observed > upper:
        errors.append("throughput_above_confidence_upper_bound")
    body = {
        "observed_cycle_throughput": observed,
        "throughput_unit": unit,
        "cycle_execution_cap": cap,
        "confidence_lower_bound": lower,
        "confidence_upper_bound": upper,
        "observed_run_id": _text(_first(value, "observed_run_id", "run_id")),
    }
    if errors:
        return body, errors
    identity_body = {key: item for key, item in body.items() if item is not None}
    body["throughput_evidence_id"] = _content_id(
        "throughput-evidence",
        _first(value, "throughput_evidence_id", "evidence_id", "measurement_id"),
        identity_body,
    )
    body["throughput_evidence_sha256"] = _canonical_sha256(identity_body)
    return body, []


def cycle_reachability_gate(
    acceptance_scale: object,
    throughput_evidence: object,
) -> dict[str, Any]:
    """Return a deterministic reachability packet without inventing domain facts."""

    scale, scale_errors = _normalize_scale(acceptance_scale)
    throughput, throughput_errors = _normalize_throughput(throughput_evidence)
    reasons = [*scale_errors, *throughput_errors]
    if not reasons and scale.get("scale_unit") != throughput.get("throughput_unit"):
        reasons.append("scale_throughput_unit_mismatch")
    if reasons:
        return {
            "gate": "G-CYCLE-REACH",
            "contract_version": 1,
            "applicability": "not_evaluated",
            "evaluation_status": "not_evaluated",
            "reachability_verdict": "indeterminate",
            "acceptance_scale": scale,
            "throughput_evidence": throughput,
            "unreachable_within_cycle": False,
            "long_run_launch_required": False,
            "harvest_validation_required": False,
            "constrains_disposition": False,
            "not_evaluated_reasons": reasons,
            "status": "not_evaluated",
        }

    required = float(scale["required_scale"])
    observed = float(throughput["observed_cycle_throughput"])
    cap = float(throughput["cycle_execution_cap"])
    lower_value = throughput.get("confidence_lower_bound")
    upper_value = throughput.get("confidence_upper_bound")
    lower = float(observed if lower_value is None else lower_value)
    upper = float(observed if upper_value is None else upper_value)
    lower_capacity = lower * cap
    upper_capacity = upper * cap
    if upper_capacity < required:
        verdict = "unreachable"
    elif lower_capacity >= required:
        verdict = "reachable"
    else:
        verdict = "indeterminate"
    unreachable = verdict == "unreachable"
    body = {
        "gate": "G-CYCLE-REACH",
        "contract_version": 1,
        "applicability": "applicable",
        "evaluation_status": "fail"
        if unreachable
        else ("pass" if verdict == "reachable" else "not_evaluated"),
        "reachability_verdict": verdict,
        "acceptance_scale": scale,
        "throughput_evidence": throughput,
        "required_scale": required,
        "observed_cycle_throughput": observed,
        "cycle_execution_cap": cap,
        "projected_cycle_capacity_lower": lower_capacity,
        "projected_cycle_capacity_upper": upper_capacity,
        "unreachable_within_cycle": unreachable,
        "long_run_launch_required": unreachable,
        "harvest_validation_required": unreachable,
        "constrains_disposition": unreachable,
        "allowed_dispositions": [
            "goal_productive",
            "terminal_blocked",
            "user_escalation",
        ],
        "allowed_task_kinds": [
            "long_run_launch",
            "throughput_improvement",
            "residual_descope",
            "descope_with_residual",
            "terminal_blocked",
            "terminal_blocker",
            "user_escalation",
        ],
        "status": "block" if unreachable else verdict,
    }
    body["cycle_reachability_sha256"] = _canonical_sha256(body)
    return body


def verify_cycle_reachability_digest(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    digest = str(value.get("cycle_reachability_sha256") or "").strip().lower()
    body = {
        key: item for key, item in value.items() if key != "cycle_reachability_sha256"
    }
    return len(digest) == 64 and digest == _canonical_sha256(body)


__all__ = ["cycle_reachability_gate", "verify_cycle_reachability_digest"]
