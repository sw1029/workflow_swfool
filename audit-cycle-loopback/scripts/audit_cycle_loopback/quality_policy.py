from __future__ import annotations

from typing import Any

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
