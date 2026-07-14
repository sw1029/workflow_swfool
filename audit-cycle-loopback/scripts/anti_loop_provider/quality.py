from __future__ import annotations

import math

from .common import *


METRIC_APPLICABILITY_STATUSES = {
    "applicable",
    "not_applicable",
    "insufficient_evidence",
    "invalid_contract",
}
METRIC_POLICY_CONTRACT_ERROR_CODES = {
    "declared_metric_id_malformed",
    "metric_alias_contract_malformed",
    "metric_policy_contract_malformed",
}
OPAQUE_ID_MAX_LENGTH = 256


def _opaque_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > OPAQUE_ID_MAX_LENGTH:
        return None
    return normalized


def _reason_code(value: Any, *, fallback: str | None) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return fallback
    normalized = _opaque_id(value)
    if normalized is None or not normalized[0].isascii() or not normalized[0].isalnum() or any(
        not character.isascii() or not (character.isalnum() or character in "._-")
        for character in normalized
    ):
        return "applicability_reason_code_malformed"
    return normalized


def _legacy_applicability_projection(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and all(
            isinstance(row, dict)
            and str(row.get("evaluation_status") or "").strip().lower() == "applicable"
            and row.get("reason_code") == "legacy_declared_metric"
            for row in value.values()
        )
    )

def _string_items(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [normalized for item in value if (normalized := _opaque_id(item)) is not None]


def _string_items_contract(value: Any, *, absent_allowed: bool = False) -> tuple[list[str], bool]:
    """Return bounded string items plus shape validity without stringifying rejected values."""
    if value is None:
        return ([], absent_allowed)
    if isinstance(value, str):
        normalized = _opaque_id(value)
        return ([normalized], True) if normalized is not None else ([], False)
    if not isinstance(value, (list, tuple, set)):
        return ([], False)
    items: list[str] = []
    valid = True
    for item in value:
        normalized = _opaque_id(item)
        if normalized is None:
            valid = False
            continue
        items.append(normalized)
    return (items, valid)


def _opaque_id_list_valid(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return _opaque_id(value) is not None
    return isinstance(value, (list, tuple, set)) and all(
        _opaque_id(item) is not None for item in value
    )


def _normalize_metric_applicability(value: Any, *, supplied: bool) -> dict[str, Any]:
    if not supplied:
        return {
            "evaluation_status": "applicable",
            "reason_code": "legacy_declared_metric",
            "required_body_class_ids": [],
            "missing_body_class_ids": [],
        }
    if isinstance(value, bool):
        value = {"evaluation_status": "applicable" if value else "not_applicable"}
    elif isinstance(value, str):
        value = {"evaluation_status": value}
    if not isinstance(value, dict):
        return {
            "evaluation_status": "invalid_contract",
            "reason_code": "applicability_row_malformed",
            "required_body_class_ids": [],
            "missing_body_class_ids": [],
        }
    status = str(value.get("evaluation_status") or value.get("status") or "").strip().lower()
    boolean_status = value.get("applicable")
    if isinstance(boolean_status, bool):
        from_boolean = "applicable" if boolean_status else "not_applicable"
        if status and status != from_boolean:
            status = "invalid_contract"
        elif not status:
            status = from_boolean
    required_value = value.get("required_body_class_ids") if "required_body_class_ids" in value else value.get("required_body_classes")
    missing_value = value.get("missing_body_class_ids") if "missing_body_class_ids" in value else value.get("missing_body_classes")
    evidence_value = value.get("evidence_ids")
    required = _string_items(required_value)
    missing = _string_items(missing_value)
    opaque_ids_valid = all(
        _opaque_id_list_valid(item) for item in (required_value, missing_value, evidence_value)
    )
    if not opaque_ids_valid:
        status = "invalid_contract"
    if status == "applicable" and missing:
        status = "insufficient_evidence"
    if status not in METRIC_APPLICABILITY_STATUSES:
        status = "invalid_contract"
    return {
        "evaluation_status": status,
        "reason_code": _reason_code(
            value.get("reason_code"),
            fallback="applicability_opaque_id_malformed" if not opaque_ids_valid else None,
        ),
        "required_body_class_ids": required,
        "missing_body_class_ids": missing,
        "evidence_ids": _string_items(evidence_value),
    }


def normalize_quality_delta_policy(value: Any) -> dict[str, Any]:
    """Normalize an explicit adapter-owned metric-key/alias contract."""
    if isinstance(value, (list, tuple, set)):
        raw_keys = value
        raw_aliases: Any = {}
    elif isinstance(value, dict):
        raw_keys = next(
            (
                value[key]
                for key in ("declared_keys", "keys", "quality_delta_keys", "metric_keys", "axes")
                if key in value and value[key] is not None
            ),
            [],
        )
        raw_aliases = next(
            (
                value[key]
                for key in ("aliases", "quality_metric_aliases", "metric_aliases")
                if key in value and value[key] is not None
            ),
            {},
        )
        raw_applicability = value.get("applicability")
        alternate_applicability = value.get("metric_applicability")
        applicability_flag_conflict = bool(
            value.get("applicability_supplied") is False
            and any(
                mapping is not None and not _legacy_applicability_projection(mapping)
                for mapping in (raw_applicability, alternate_applicability)
            )
        )
        if value.get("applicability_supplied") is False and not applicability_flag_conflict:
            raw_applicability = None
            alternate_applicability = None
    else:
        raw_keys = []
        raw_aliases = {}
        raw_applicability = None
        alternate_applicability = None
        applicability_flag_conflict = False

    if not isinstance(value, dict):
        raw_applicability = None
        alternate_applicability = None
        applicability_flag_conflict = False

    raw_key_items, declared_keys_valid = _string_items_contract(raw_keys)
    keys = list(dict.fromkeys(raw_key_items))
    aliases: dict[str, list[str]] = {}
    alias_invalid_keys: set[str] = set()
    alias_contract_valid = isinstance(raw_aliases, dict)
    if isinstance(raw_aliases, dict):
        for key in keys:
            alias_items, alias_items_valid = _string_items_contract(
                raw_aliases.get(key),
                absent_allowed=True,
            )
            if not alias_items_valid:
                alias_invalid_keys.add(key)
            candidates = [key, *alias_items]
            aliases[key] = list(dict.fromkeys(candidates))
        for alias_key, alias_value in raw_aliases.items():
            _, entry_valid = _string_items_contract(alias_value, absent_allowed=True)
            if _opaque_id(alias_key) is None or not entry_valid:
                alias_contract_valid = False
                if isinstance(alias_key, str) and alias_key in keys:
                    alias_invalid_keys.add(alias_key)
    else:
        aliases = {key: [key] for key in keys}
    inherited_error_codes = [
        code
        for code in (_string_items(value.get("policy_contract_error_codes")) if isinstance(value, dict) else [])
        if code in METRIC_POLICY_CONTRACT_ERROR_CODES
    ]
    policy_contract_error_codes: list[str] = list(dict.fromkeys(inherited_error_codes))
    if isinstance(value, dict) and value.get("policy_contract_invalid") and not policy_contract_error_codes:
        policy_contract_error_codes.append("metric_policy_contract_malformed")
    if not declared_keys_valid:
        policy_contract_error_codes.append("declared_metric_id_malformed")
    if not alias_contract_valid or alias_invalid_keys:
        policy_contract_error_codes.append("metric_alias_contract_malformed")
    if applicability_flag_conflict:
        policy_contract_error_codes.append("metric_policy_contract_malformed")
    for applicability_value in (raw_applicability, alternate_applicability):
        if isinstance(applicability_value, dict) and any(
            _opaque_id(metric_id) is None for metric_id in applicability_value
        ):
            policy_contract_error_codes.append("metric_policy_contract_malformed")
    policy_contract_error_codes = list(dict.fromkeys(policy_contract_error_codes))
    policy_contract_invalid = bool(policy_contract_error_codes)
    applicability_conflict = (
        raw_applicability is not None
        and alternate_applicability is not None
        and raw_applicability != alternate_applicability
    )
    applicability_source = raw_applicability if raw_applicability is not None else alternate_applicability
    applicability_supplied = applicability_source is not None
    applicability_mapping = applicability_source if isinstance(applicability_source, dict) else {}
    applicability = {
        key: _normalize_metric_applicability(
            applicability_mapping.get(key),
            supplied=applicability_supplied,
        )
        for key in keys
    }
    if applicability_conflict or (applicability_supplied and not isinstance(applicability_source, dict)):
        for key in keys:
            applicability[key] = {
                **applicability[key],
                "evaluation_status": "invalid_contract",
                "reason_code": "applicability_mapping_conflict" if applicability_conflict else "applicability_mapping_malformed",
            }
    invalid = [key for key in keys if applicability[key]["evaluation_status"] == "invalid_contract"]
    if policy_contract_invalid:
        invalid = list(keys)
    insufficient = [key for key in keys if applicability[key]["evaluation_status"] == "insufficient_evidence"]
    not_applicable = [key for key in keys if applicability[key]["evaluation_status"] == "not_applicable"]
    decision_keys = [] if policy_contract_invalid or invalid else [key for key in keys if applicability[key]["evaluation_status"] == "applicable"]
    return {
        "declared_keys": keys,
        "keys": decision_keys,
        "aliases": aliases,
        "applicability": applicability,
        "applicability_supplied": applicability_supplied,
        "not_applicable_fields": not_applicable,
        "insufficient_evidence_fields": insufficient,
        "invalid_contract_fields": invalid,
        "policy_contract_invalid": policy_contract_invalid,
        "policy_contract_error_codes": policy_contract_error_codes,
        "supplied": bool(keys),
    }


def apply_quality_policy_compatibility(
    policy: Any,
    compatibility: dict[str, Any],
    *,
    policy_error: str | None = None,
) -> dict[str, Any]:
    """Project the existing gate-compatibility receipt onto decision metric IDs."""
    normalized = normalize_quality_delta_policy(policy)
    declared = normalized["declared_keys"]
    if not declared:
        return normalized
    gate_status = str(compatibility.get("gate_compatibility_status") or "not_evaluated").strip().lower()
    basis = str(compatibility.get("compatibility_basis") or "").strip().lower()
    if policy_error or basis in {
        "adapter_hook_return_contract_invalid",
        "adapter_hook_identity_echo_invalid",
        "gate_artifact_compatibility_signature_incompatible",
        "hook_error",
    }:
        projected_status = "invalid_contract"
        reason_code = "metric_policy_or_compatibility_invalid"
    elif gate_status == "incompatible":
        projected_status = "not_applicable"
        reason_code = "artifact_metric_incompatible"
    elif gate_status == "compatible":
        return normalized
    elif basis == "mapping_not_supplied":
        # The compatibility hook is optional. Its absence must not invalidate
        # a policy that already carries applicability rows, or a legacy
        # declared-key policy. Metric evidence is still checked below.
        return normalized
    else:
        projected_status = "insufficient_evidence"
        reason_code = "artifact_metric_compatibility_unresolved"
    projected = {
        key: {
            **normalized["applicability"].get(key, {}),
            "evaluation_status": projected_status,
            "reason_code": reason_code,
        }
        for key in declared
    }
    return normalize_quality_delta_policy(
        {
            "keys": declared,
            "aliases": normalized["aliases"],
            "applicability": projected,
        }
    )


def _numeric_metric_value(
    mapping: dict[str, Any],
    key: str,
    aliases: dict[str, Any] | None = None,
) -> tuple[bool, float | None]:
    candidates = _string_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate not in mapping:
            continue
        value = mapping.get(candidate)
        if isinstance(value, bool):
            return False, None
        if isinstance(value, (int, float)):
            try:
                numeric = float(value)
            except OverflowError:
                return False, None
            return (True, numeric) if math.isfinite(numeric) else (False, None)
        if isinstance(value, str):
            try:
                numeric = float(value.strip())
                return (True, numeric) if math.isfinite(numeric) else (False, None)
            except ValueError:
                return False, None
        return False, None
    return False, None


def quality_metric_value(
    quality: dict[str, Any],
    key: str,
    aliases: dict[str, Any] | None = None,
) -> float:
    candidates = _string_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate in quality:
            return float_value(quality.get(candidate))
    return 0.0

def high_water_metric_value(
    high_water: dict[str, Any],
    key: str,
    aliases: dict[str, Any] | None = None,
) -> float:
    candidates = _string_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate in high_water:
            return float_value(high_water.get(candidate))
    return 0.0


def quality_high_water_for_policy(high_water: dict[str, Any], policy: Any) -> dict[str, Any]:
    normalized = normalize_quality_delta_policy(policy)
    result: dict[str, Any] = {}
    for key in normalized["keys"]:
        present, metric_value = _numeric_metric_value(high_water, key, normalized["aliases"])
        if present and metric_value is not None:
            result[key] = metric_value
    result["ever_provider_dispatch"] = bool_value(high_water.get("ever_provider_dispatch"))
    return result


def public_quality_delta_policy(policy: Any) -> dict[str, Any]:
    """Preserve the legacy packet shape when no additive applicability is used."""
    normalized = normalize_quality_delta_policy(policy)
    if not normalized["applicability_supplied"] and not normalized["policy_contract_invalid"]:
        return {
            "keys": normalized["declared_keys"],
            "aliases": normalized["aliases"],
            "supplied": normalized["supplied"],
        }
    return normalized


def metric_stall_observation_allowed(
    evaluation_status: Any,
    *,
    policy_supplied: bool,
    producer_absence_reason: Any = None,
) -> bool:
    """Separate evaluated metrics from legacy producer-absence observations."""
    status = str(evaluation_status or "not_evaluated").strip().lower()
    if status == "evaluated":
        return True
    return bool(status == "not_evaluated" and not policy_supplied and producer_absence_reason)

def coverage_quality_delta_gate(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    epsilon: float,
    quality_delta_policy: Any = None,
) -> dict[str, Any]:
    policy = normalize_quality_delta_policy(quality_delta_policy)
    keys = policy["keys"]
    try:
        epsilon_value = float(epsilon) if not isinstance(epsilon, bool) else float("nan")
    except (OverflowError, TypeError, ValueError):
        epsilon_value = float("nan")
    epsilon_valid = math.isfinite(epsilon_value) and epsilon_value >= 0
    effective_epsilon = epsilon_value if epsilon_valid else 0.0
    current: dict[str, float] = {}
    previous: dict[str, float] = {}
    missing_observations: list[str] = []
    previous_binding_count = sum(
        1
        for key in keys
        if any(candidate in prev_high for candidate in policy["aliases"].get(key, [key]))
    )
    baseline_absent = bool(keys) and previous_binding_count == 0
    for key in keys:
        current_present, current_value = _numeric_metric_value(quality, key, policy["aliases"])
        previous_present, previous_value = _numeric_metric_value(prev_high, key, policy["aliases"])
        if current_present and current_value is not None:
            current[key] = current_value
        if previous_present and previous_value is not None:
            previous[key] = previous_value
        elif baseline_absent:
            previous[key] = 0.0
        if not current_present or (not previous_present and not baseline_absent):
            missing_observations.append(key)
    invalid_contract_fields = list(policy["invalid_contract_fields"])
    if not epsilon_valid:
        invalid_contract_fields = list(dict.fromkeys([*invalid_contract_fields, *policy["declared_keys"]]))
    insufficient_evidence_fields = sorted(set([*policy["insufficient_evidence_fields"], *missing_observations]))
    evaluated = bool(keys) and not invalid_contract_fields and not insufficient_evidence_fields
    improved_fields = [
        key
        for key in keys
        if evaluated and current[key] > previous[key] + (effective_epsilon if key.endswith("_ratio") else 0.0)
    ]
    provider_dispatch_delta = provider_request_count > 0 and not bool_value(prev_high.get("ever_provider_dispatch"))
    previous_high_water_all_zero = evaluated and all(previous[key] <= 0 for key in keys)
    current_quality_all_zero = evaluated and all(current[key] <= 0 for key in keys)
    if policy.get("policy_contract_invalid") or invalid_contract_fields:
        evaluation_status = "invalid_contract"
    elif insufficient_evidence_fields:
        evaluation_status = "insufficient_evidence"
    elif not policy["supplied"]:
        evaluation_status = "not_evaluated"
    elif not keys and policy["not_applicable_fields"]:
        evaluation_status = "not_applicable"
    else:
        evaluation_status = "evaluated"
    return {
        "gate": "G-COV",
        "quality_delta_pass": bool(improved_fields),
        "improved_fields": improved_fields,
        "current_quality_vector": current,
        "previous_high_water_vector": previous,
        "provider_dispatch_delta": provider_dispatch_delta,
        "previous_high_water_all_zero": previous_high_water_all_zero,
        "current_quality_all_zero": current_quality_all_zero,
        "high_water_all_zero": previous_high_water_all_zero and current_quality_all_zero,
        "quality_delta_policy": policy,
        "quality_delta_policy_supplied": policy["supplied"],
        "not_applicable_fields": policy["not_applicable_fields"],
        "insufficient_evidence_fields": insufficient_evidence_fields,
        "invalid_contract_fields": invalid_contract_fields,
        "evaluation_status": evaluation_status,
        "status": "pass" if improved_fields else ("block" if evaluation_status == "evaluated" else evaluation_status),
    }

def provider_scale_dispatch_gate(
    prev_high: dict[str, Any],
    coverage_gate: dict[str, Any],
    provider_request_count: int,
) -> dict[str, Any]:
    dispatch_required = (
        not bool_value(prev_high.get("ever_provider_dispatch"))
        and bool_value(coverage_gate.get("high_water_all_zero"))
        and provider_request_count == 0
    )
    return {
        "gate": "G-DISPATCH",
        "ever_provider_dispatch": bool_value(prev_high.get("ever_provider_dispatch")) or provider_request_count > 0,
        "provider_request_count": provider_request_count,
        "high_water_all_zero": bool_value(coverage_gate.get("high_water_all_zero")),
        "dispatch_required": dispatch_required,
        "hard_stop_required": dispatch_required,
        "constrains_disposition": dispatch_required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "blocked_surface_only_work": dispatch_required,
        "status": "block" if dispatch_required else "ok",
    }
