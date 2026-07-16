from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .common import (
    METRIC_APPLICABILITY_STATUSES,
    METRIC_POLICY_CONTRACT_ERROR_CODES,
    applicability_reason_code,
    legacy_applicability_projection,
    opaque_id,
    opaque_id_list_valid,
    policy_items,
    policy_items_contract,
)


@dataclass(frozen=True)
class RawPolicy:
    keys: Any
    aliases: Any
    applicability: Any
    alternate_applicability: Any
    applicability_flag_conflict: bool


@dataclass(frozen=True)
class PolicyBindings:
    keys: list[str]
    aliases: dict[str, list[str]]
    errors: list[str]


def normalize_metric_applicability(value: Any, *, supplied: bool) -> dict[str, Any]:
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
        }
    status = (
        str(value.get("evaluation_status") or value.get("status") or "").strip().lower()
    )
    boolean_status = value.get("applicable")
    if isinstance(boolean_status, bool):
        from_boolean = "applicable" if boolean_status else "not_applicable"
        if status and status != from_boolean:
            status = "invalid_contract"
        elif not status:
            status = from_boolean
    required_value = (
        value.get("required_body_class_ids")
        if "required_body_class_ids" in value
        else value.get("required_body_classes")
    )
    missing_value = (
        value.get("missing_body_class_ids")
        if "missing_body_class_ids" in value
        else value.get("missing_body_classes")
    )
    evidence_value = value.get("evidence_ids")
    required = policy_items(required_value)
    missing = policy_items(missing_value)
    opaque_ids_valid = all(
        opaque_id_list_valid(item)
        for item in (required_value, missing_value, evidence_value)
    )
    if not opaque_ids_valid:
        status = "invalid_contract"
    if status == "applicable" and missing:
        status = "insufficient_evidence"
    if status not in METRIC_APPLICABILITY_STATUSES:
        status = "invalid_contract"
    return {
        "evaluation_status": status,
        "reason_code": applicability_reason_code(
            value.get("reason_code"),
            fallback="applicability_opaque_id_malformed"
            if not opaque_ids_valid
            else None,
        ),
        "required_body_class_ids": required,
        "missing_body_class_ids": missing,
        "evidence_ids": policy_items(evidence_value),
    }


def _raw_policy(value: Any) -> RawPolicy:
    if isinstance(value, (list, tuple, set)):
        return RawPolicy(value, {}, None, None, False)
    if not isinstance(value, dict):
        return RawPolicy([], {}, None, None, False)
    raw_keys = next(
        (
            value[key]
            for key in (
                "declared_keys",
                "keys",
                "quality_delta_keys",
                "metric_keys",
                "axes",
            )
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
    applicability = value.get("applicability")
    alternate = value.get("metric_applicability")
    flag_conflict = bool(
        value.get("applicability_supplied") is False
        and any(
            mapping is not None and not legacy_applicability_projection(mapping)
            for mapping in (applicability, alternate)
        )
    )
    if value.get("applicability_supplied") is False and not flag_conflict:
        applicability, alternate = None, None
    return RawPolicy(raw_keys, raw_aliases, applicability, alternate, flag_conflict)


def _policy_bindings(value: Any, raw: RawPolicy) -> PolicyBindings:
    raw_key_items, declared_keys_valid = policy_items_contract(raw.keys)
    keys = list(dict.fromkeys(raw_key_items))
    aliases: dict[str, list[str]] = {}
    alias_invalid_keys: set[str] = set()
    alias_contract_valid = isinstance(raw.aliases, dict)
    if isinstance(raw.aliases, dict):
        for key in keys:
            supplied, supplied_valid = policy_items_contract(
                raw.aliases.get(key), absent_allowed=True
            )
            if not supplied_valid:
                alias_invalid_keys.add(key)
            aliases[key] = list(dict.fromkeys([key, *supplied]))
        for alias_key, alias_value in raw.aliases.items():
            _, entry_valid = policy_items_contract(alias_value, absent_allowed=True)
            if opaque_id(alias_key) is None or not entry_valid:
                alias_contract_valid = False
                if isinstance(alias_key, str) and alias_key in keys:
                    alias_invalid_keys.add(alias_key)
    else:
        aliases = {key: [key] for key in keys}
    inherited = [
        code
        for code in (
            policy_items(value.get("policy_contract_error_codes"))
            if isinstance(value, dict)
            else []
        )
        if code in METRIC_POLICY_CONTRACT_ERROR_CODES
    ]
    errors = list(dict.fromkeys(inherited))
    if isinstance(value, dict) and value.get("policy_contract_invalid") and not errors:
        errors.append("metric_policy_contract_malformed")
    if not declared_keys_valid:
        errors.append("declared_metric_id_malformed")
    if not alias_contract_valid or alias_invalid_keys:
        errors.append("metric_alias_contract_malformed")
    if raw.applicability_flag_conflict:
        errors.append("metric_policy_contract_malformed")
    for applicability_value in (raw.applicability, raw.alternate_applicability):
        if isinstance(applicability_value, dict) and any(
            opaque_id(metric_id) is None for metric_id in applicability_value
        ):
            errors.append("metric_policy_contract_malformed")
    return PolicyBindings(keys, aliases, list(dict.fromkeys(errors)))


def _normalized_projection(raw: RawPolicy, bindings: PolicyBindings) -> dict[str, Any]:
    conflict = (
        raw.applicability is not None
        and raw.alternate_applicability is not None
        and raw.applicability != raw.alternate_applicability
    )
    source = (
        raw.applicability
        if raw.applicability is not None
        else raw.alternate_applicability
    )
    supplied = source is not None
    mapping = source if isinstance(source, dict) else {}
    applicability = {
        key: normalize_metric_applicability(mapping.get(key), supplied=supplied)
        for key in bindings.keys
    }
    if conflict or (supplied and not isinstance(source, dict)):
        for key in bindings.keys:
            applicability[key] = {
                **applicability[key],
                "evaluation_status": "invalid_contract",
                "reason_code": "applicability_mapping_conflict"
                if conflict
                else "applicability_mapping_malformed",
            }
    invalid = [
        key
        for key in bindings.keys
        if applicability[key]["evaluation_status"] == "invalid_contract"
    ]
    if bindings.errors:
        invalid = list(bindings.keys)
    insufficient = [
        key
        for key in bindings.keys
        if applicability[key]["evaluation_status"] == "insufficient_evidence"
    ]
    not_applicable = [
        key
        for key in bindings.keys
        if applicability[key]["evaluation_status"] == "not_applicable"
    ]
    return {
        "declared_keys": bindings.keys,
        "keys": []
        if bindings.errors or invalid
        else [
            key
            for key in bindings.keys
            if applicability[key]["evaluation_status"] == "applicable"
        ],
        "aliases": bindings.aliases,
        "applicability": applicability,
        "applicability_supplied": supplied,
        "not_applicable_fields": not_applicable,
        "insufficient_evidence_fields": insufficient,
        "invalid_contract_fields": invalid,
        "policy_contract_invalid": bool(bindings.errors),
        "policy_contract_error_codes": bindings.errors,
        "supplied": bool(bindings.keys),
    }


def normalize_quality_delta_policy(value: Any) -> dict[str, Any]:
    raw = _raw_policy(value)
    return _normalized_projection(raw, _policy_bindings(value, raw))


def explicit_quality_delta_policy(
    contract: dict[str, Any] | None, payload: dict[str, Any] | None
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for source in (payload, contract):
        if not isinstance(source, dict):
            continue
        policy = source.get("quality_delta_policy")
        if policy is not None:
            candidates.append(normalize_quality_delta_policy(policy))
        elif source.get("quality_delta_keys") is not None:
            candidates.append(
                normalize_quality_delta_policy(
                    {
                        "keys": source.get("quality_delta_keys"),
                        "aliases": source.get("quality_metric_aliases") or {},
                    }
                )
            )
    if not candidates:
        return normalize_quality_delta_policy(None)
    comparable = [
        json.dumps(
            {
                "declared_keys": sorted(item["declared_keys"]),
                "policy_contract_invalid": item["policy_contract_invalid"],
                "policy_contract_error_codes": sorted(
                    item["policy_contract_error_codes"]
                ),
                "aliases": {
                    key: sorted(set(item["aliases"].get(key, [key])))
                    for key in sorted(item["declared_keys"])
                },
                "applicability": {
                    key: {
                        "evaluation_status": item["applicability"]
                        .get(key, {})
                        .get("evaluation_status"),
                        "required_body_class_ids": sorted(
                            set(
                                item["applicability"]
                                .get(key, {})
                                .get("required_body_class_ids")
                                or []
                            )
                        ),
                        "missing_body_class_ids": sorted(
                            set(
                                item["applicability"]
                                .get(key, {})
                                .get("missing_body_class_ids")
                                or []
                            )
                        ),
                    }
                    for key in sorted(item["declared_keys"])
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for item in candidates
    ]
    if len(set(comparable)) == 1:
        return candidates[0]
    declared = list(
        dict.fromkeys(key for item in candidates for key in item["declared_keys"])
    )
    aliases = {
        key: list(
            dict.fromkeys(
                alias
                for item in candidates
                for alias in item["aliases"].get(key, [key])
            )
        )
        for key in declared
    }
    return normalize_quality_delta_policy(
        {
            "keys": declared,
            "aliases": aliases,
            "applicability": {
                key: {
                    "evaluation_status": "invalid_contract",
                    "reason_code": "payload_contract_policy_conflict",
                }
                for key in declared
            },
        }
    )
