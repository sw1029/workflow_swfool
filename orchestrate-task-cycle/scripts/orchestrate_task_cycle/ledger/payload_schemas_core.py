from __future__ import annotations

from .payload_schema_common import (
    exact_object,
    exact_rows_payload,
    require_bool,
    require_non_negative_int,
    require_opaque_id,
    require_unique_opaque_ids,
)


_REGISTRY_PROJECTION_FIELDS = frozenset(
    {
        "artifact_id",
        "semantic_progress",
        "authoritative_semantic_progress",
        "goal_productive",
        "progress_verdict",
    }
)
_REGISTRY_PROGRESS_VERDICTS = {
    "advanced",
    "blocked",
    "no_progress",
    "not_evaluated",
    "partial",
    "stalled",
}
_DEDUP_ROW_FIELDS = frozenset(
    {
        "symbol",
        "scope",
        "first_seen_evidence_id",
        "occurrence_count",
        "consumed_input_fp",
        "target_unit_fp",
        "target_unit_count",
        "observed_output_classes",
        "last_observed_output_class",
        "last_observed_material_delta",
        "artifact_fingerprint",
        "artifact_count_fingerprint",
        "last_evidence_id",
        "status",
    }
)
_DEDUP_REQUIRED_FIELDS = frozenset(
    {
        "symbol",
        "scope",
        "occurrence_count",
        "observed_output_classes",
        "last_observed_output_class",
        "last_observed_material_delta",
        "status",
    }
)


def validate_registry_projection_payload(value: object) -> None:
    payload = exact_object(
        value,
        allowed=_REGISTRY_PROJECTION_FIELDS,
        required=frozenset({"artifact_id"}),
        label="registry-projection-v1",
    )
    require_opaque_id(payload["artifact_id"], label="registry artifact_id")
    for field in (
        "semantic_progress",
        "authoritative_semantic_progress",
        "goal_productive",
    ):
        if field in payload:
            require_bool(payload[field], label=f"registry {field}")
    if (
        "progress_verdict" in payload
        and payload["progress_verdict"] not in _REGISTRY_PROGRESS_VERDICTS
    ):
        raise ValueError("registry progress_verdict is outside its closed vocabulary")


def validate_ledger_projection_payload(value: object) -> None:
    rows = exact_rows_payload(value, label="ledger-projection-v1")
    for row in rows:
        parsed = exact_object(
            row,
            allowed=frozenset({"evidence_id"}),
            required=frozenset({"evidence_id"}),
            label="ledger-projection-v1 row",
        )
        require_opaque_id(parsed["evidence_id"], label="ledger evidence_id")


def validate_dedup_symbol_registry_payload(value: object) -> None:
    rows = exact_rows_payload(value, label="dedup-symbol-registry-v1")
    seen_symbols: set[str] = set()
    for row in rows:
        parsed = exact_object(
            row,
            allowed=_DEDUP_ROW_FIELDS,
            required=_DEDUP_REQUIRED_FIELDS,
            label="dedup-symbol-registry-v1 row",
        )
        symbol = require_opaque_id(parsed["symbol"], label="dedup symbol")
        if symbol in seen_symbols:
            raise ValueError("dedup-symbol-registry-v1 rows duplicate symbol")
        seen_symbols.add(symbol)
        require_opaque_id(parsed["scope"], label="dedup scope")
        require_non_negative_int(
            parsed["occurrence_count"], label="dedup occurrence_count"
        )
        require_unique_opaque_ids(
            parsed["observed_output_classes"],
            label="dedup observed_output_classes",
        )
        require_opaque_id(
            parsed["last_observed_output_class"],
            label="dedup last_observed_output_class",
        )
        require_non_negative_int(
            parsed["last_observed_material_delta"],
            label="dedup last_observed_material_delta",
        )
        require_opaque_id(parsed["status"], label="dedup status")
        for field in (
            "first_seen_evidence_id",
            "consumed_input_fp",
            "target_unit_fp",
            "artifact_fingerprint",
            "artifact_count_fingerprint",
            "last_evidence_id",
        ):
            if parsed.get(field) is not None:
                require_opaque_id(parsed[field], label=f"dedup {field}")
        if parsed.get("target_unit_count") is not None:
            require_non_negative_int(
                parsed["target_unit_count"], label="dedup target_unit_count"
            )


__all__ = [
    "validate_dedup_symbol_registry_payload",
    "validate_ledger_projection_payload",
    "validate_registry_projection_payload",
]
