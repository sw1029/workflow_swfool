"""Aggregate structural metrics without trusting caller-authored usage claims."""

from __future__ import annotations

from pathlib import Path
from typing import Any


STRUCTURAL_FIELDS = (
    "files_opened_count",
    "files_written_count",
    "target_context_bytes",
    "context_bytes",
    "work_order_bytes",
    "machine_input_bytes",
    "preparation_bytes",
    "owner_result_bytes",
    "semantic_bytes",
    "raw_bytes_read",
    "result_bytes",
    "compact_payload_bytes",
    "cas_newly_written_bytes",
    "cas_reused_bytes",
    "model_visible_bytes",
    "model_call_count",
    "model_authored_mechanical_bytes",
    "inline_payload_bytes",
)
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens")


def compiler_efficiency_projection(
    root: Path, events: list[dict[str, Any]]
) -> dict[str, Any]:
    root.resolve(strict=True)
    totals = {field: 0 for field in STRUCTURAL_FIELDS}
    invalid_structural = 0
    compiler_events = 0
    legacy_usage = 0
    unattested_usage = 0
    invalid_usage = 0
    for event in events:
        metrics = event.get("compiler_metrics")
        if not isinstance(metrics, dict):
            continue
        compiler_events += 1
        for field in STRUCTURAL_FIELDS:
            value = metrics.get(field, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                invalid_structural += 1
                continue
            totals[field] += value
        usage_version = metrics.get("usage_receipt_schema_version")
        if usage_version == 1:
            legacy_usage += 1
        elif usage_version == 2:
            if (
                metrics.get("usage_aggregate_eligible") is False
                and metrics.get("usage_provenance_status")
                == "caller_asserted_unverified"
            ):
                unattested_usage += 1
            else:
                invalid_usage += 1
        elif metrics.get("usage_aggregate_eligible") is True:
            invalid_usage += 1
    token_totals = {field: 0 for field in TOKEN_FIELDS}
    return {
        "schema_version": 2,
        "compiler_stage_event_count": compiler_events,
        "structural_totals": totals,
        "invalid_structural_metric_count": invalid_structural,
        "usage": {
            "verified_receipt_count": 0,
            "duplicate_receipt_count": 0,
            "conflicting_receipt_count": 0,
            "legacy_v1_excluded_count": legacy_usage,
            "unattested_v2_excluded_count": unattested_usage,
            "invalid_v2_excluded_count": invalid_usage,
            "aggregate_eligible": False,
            **token_totals,
        },
        "runtime_comparison": {
            "status": "not_evaluated",
            "reason": "trusted_runtime_attestation_not_available",
        },
    }


__all__ = ["STRUCTURAL_FIELDS", "compiler_efficiency_projection"]
