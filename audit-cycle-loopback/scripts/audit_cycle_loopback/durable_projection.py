from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_DURABLE_SENSITIVE_KEYS = {
    "anti_loop_handoff",
    "artifact_path_or_store_ref",
    "blockers",
    "changed_files",
    "changed_verifier_source_paths",
    "duplicate_key_paths",
    "error",
    "evidence_paths",
    "legacy_attempt_identity",
    "legacy_family_key",
    "message",
    "normalization_note",
    "no_overclaim",
    "original_title",
    "path",
    "raw_source_path",
    "reason",
    "repair_task_id",
    "repo_owned_source_refs",
    "root_cause_ledger_projection",
    "sealed_blocker_families_projection",
    "source_paths",
    "task_family_label",
    "task_id",
    "task_label",
    "task_name",
    "task_pack_id",
    "task_pack_item_id",
    "task_pack_name",
    "title",
    "used_advice",
    "verifier_source_paths",
}
_DURABLE_VOLATILE_KEYS = {
    "checked_at",
    "created_at",
    "created_or_observed_at",
    "timestamp",
    "updated_at",
}
_DURABLE_SENSITIVE_KEY_PARTS = (
    "character_count",
    "char_count",
    "direct_quote",
    "interval",
    "line_number",
    "line_start",
    "line_end",
    "locator",
    "offset",
    "original_title",
    "quoted_text",
    "raw_text",
    "source_text",
    "text_span",
)
_OPAQUE_ENUM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_METRIC_VALUE_FIELDS = (
    "primary_metric_value",
    "previous_primary_metric_value",
    "primary_metric_high_water",
)
_OBSERVATION_VALUE_FIELDS = ("observed_value", "high_water_value")


def _durable_key_is_sensitive(key: str) -> bool:
    normalized = key.strip().lower()
    return bool(
        normalized in _DURABLE_SENSITIVE_KEYS
        or normalized in _DURABLE_VOLATILE_KEYS
        or normalized.endswith("_at")
        or normalized.endswith("_error")
        or normalized.endswith("_path")
        or normalized.endswith("_paths")
        or normalized.startswith("path_")
        or normalized == "raw"
        or normalized.startswith("raw_")
        or normalized.endswith("_raw")
        or normalized == "text"
        or normalized.startswith("text_")
        or normalized.endswith("_text")
        or normalized == "quote"
        or normalized.startswith("quote_")
        or normalized.endswith("_quote")
        or normalized == "title"
        or normalized.startswith("title_")
        or normalized.endswith("_title")
        or any(part in normalized for part in _DURABLE_SENSITIVE_KEY_PARTS)
    )


def _reference_looks_like_path(value: str) -> bool:
    text = value.strip()
    return bool(
        text.startswith(("/", "./", "../", "~"))
        or "/" in text
        or "\\" in text
        or re.search(
            r"(?:^|[._-])(?:md|jsonl?|ya?ml|txt|csv|parquet|py)$", text, re.IGNORECASE
        )
    )


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _metric_value_requires_reference(value: Any, value_kind: str) -> bool:
    if value is None:
        return False
    if value_kind in {"set", "vector"}:
        return True
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return True
    return isinstance(value, str) and not _OPAQUE_ENUM_RE.fullmatch(value)


def _metric_value_reference(value: Any, value_kind: str) -> dict[str, Any]:
    digest = _canonical_sha256(value)
    if isinstance(value, dict):
        summary_kind = "vector"
        member_count = len(value)
    elif isinstance(value, (list, tuple, set, frozenset)):
        summary_kind = "collection"
        member_count = len(value)
    elif isinstance(value, str):
        summary_kind = "enum"
        member_count = 1
    else:
        summary_kind = "scalar"
        member_count = 1
    return {
        "contract_version": 1,
        "value_ref": f"metric-value-{digest}",
        "full_content_sha256": digest,
        "summary": {
            "summary_kind": summary_kind,
            "value_kind": value_kind or "unknown",
            "member_count": member_count,
        },
    }


def _privacy_safe_comparison_config(
    config: Any,
    *,
    value_kind: str,
) -> Any:
    if not isinstance(config, dict):
        return config
    projected = dict(config)
    for field in ("ordered_values", "target_value", "vector_directions"):
        supplied = projected.get(field)
        if _metric_value_requires_reference(supplied, value_kind):
            projected[field] = _metric_value_reference(supplied, value_kind)
    return projected


def _contains_metric_value_reference(value: Any) -> bool:
    if isinstance(value, dict):
        if "value_ref" in value and "full_content_sha256" in value:
            return True
        return any(_contains_metric_value_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_metric_value_reference(item) for item in value)
    return False


def _privacy_safe_primary_metric_gate(gate: dict[str, Any]) -> dict[str, Any]:
    projected = dict(gate)
    value_kind = str(projected.get("value_kind") or "").strip().lower()
    for field in _METRIC_VALUE_FIELDS:
        supplied = projected.get(field)
        if _metric_value_requires_reference(supplied, value_kind):
            projected[field] = _metric_value_reference(supplied, value_kind)
    projected["comparison_config"] = _privacy_safe_comparison_config(
        projected.get("comparison_config"),
        value_kind=value_kind,
    )
    observation = projected.get("metric_observation")
    if isinstance(observation, dict):
        observation = dict(observation)
        contract = observation.get("metric_contract")
        observation_kind = value_kind
        if isinstance(contract, dict):
            contract = dict(contract)
            observation_kind = (
                str(contract.get("value_kind") or value_kind).strip().lower()
            )
            contract["comparison_config"] = _privacy_safe_comparison_config(
                contract.get("comparison_config"),
                value_kind=observation_kind,
            )
            observation["metric_contract"] = contract
        for field in _OBSERVATION_VALUE_FIELDS:
            supplied = observation.get(field)
            if _metric_value_requires_reference(supplied, observation_kind):
                observation[field] = _metric_value_reference(
                    supplied,
                    observation_kind,
                )
        projected["metric_observation"] = observation
    if _contains_metric_value_reference(projected):
        projected["durable_value_projection_status"] = "reference_only"
    return projected


def bounded_durable_projection(value: Any, *, parent_key: str = "") -> Any:
    """Remove source-locating metadata while retaining replayable scalar state."""
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            if _durable_key_is_sensitive(key):
                continue
            if key == "findings" and isinstance(child, list):
                projected[key] = [
                    {
                        field: finding.get(field)
                        for field in ("severity", "code")
                        if finding.get(field) is not None
                    }
                    for finding in child
                    if isinstance(finding, dict)
                ]
                continue
            sanitized = bounded_durable_projection(child, parent_key=key)
            if sanitized is not None or child is None:
                projected[key] = sanitized
        if parent_key == "primary_metric_gate":
            return _privacy_safe_primary_metric_gate(projected)
        return projected
    if isinstance(value, list):
        projected_items = []
        for child in value:
            sanitized = bounded_durable_projection(child, parent_key=parent_key)
            if sanitized is not None:
                projected_items.append(sanitized)
        return projected_items
    if isinstance(value, str) and _reference_looks_like_path(value):
        if (
            parent_key.endswith("_ref")
            or parent_key.endswith("_refs")
            or parent_key.endswith("_error")
            or parent_key
            in {"action", "error", "message", "orphans", "provenance_refs"}
        ):
            return None
    return value
