"""Bounded lint for compiler-owned ledger envelopes and metric claims."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..ledger.workflow_contract import PRODUCER_EVENT_KINDS, workflow_contract_state


MAX_FINDINGS = 50
MAX_COMPILER_METRIC_FIELDS = 48
MAX_COMPILER_METRICS_BYTES = 8 * 1024
COMPILED_EVENT_KINDS = set(PRODUCER_EVENT_KINDS.values())
RUNTIME_USAGE_FIELDS = {
    "model_call_count",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
}


def _cycle_contract(root: Path, cycle_id: str) -> str:
    path = root / ".task" / "cycle" / cycle_id / "initialization.json"
    if not path.is_file():
        return "unmarked"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "invalid"
    return workflow_contract_state(value) if isinstance(value, dict) else "invalid"


def lint_compiler_contract(
    root: Path, events: list[dict[str, Any]]
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    counts = {
        "enforced_event_count": 0,
        "historical_v2_read_only_debt_count": 0,
        "invalid_envelope_count": 0,
        "unattested_runtime_claim_count": 0,
    }
    contract_cache: dict[str, str] = {}

    def add(code: str, event: dict[str, Any]) -> None:
        if len(findings) >= MAX_FINDINGS:
            return
        findings.append(
            {
                "code": code,
                "event_id": str(event.get("event_id") or "")[:255],
                "step": str(event.get("step") or "")[:128],
            }
        )

    for event in events:
        cycle_id = str(event.get("cycle_id") or "")
        first_cycle_event = cycle_id not in contract_cache
        if cycle_id not in contract_cache:
            contract_cache[cycle_id] = (
                _cycle_contract(root, cycle_id) if cycle_id else "unbound"
            )
        state = contract_cache[cycle_id]
        event_kind = event.get("event_kind")
        producer_kind = event.get("producer_kind")
        expected_kind = PRODUCER_EVENT_KINDS.get(str(producer_kind or ""))
        if state == "enforced":
            counts["enforced_event_count"] += 1
            if event_kind not in COMPILED_EVENT_KINDS or expected_kind != event_kind:
                counts["invalid_envelope_count"] += 1
                add("enforced_cycle_noncompiled_event", event)
        elif state == "historical_v2_read_only" and first_cycle_event:
            counts["historical_v2_read_only_debt_count"] += 1
            add("historical_v2_read_only_debt", event)

        metrics = event.get("compiler_metrics")
        if not isinstance(metrics, dict):
            continue
        encoded = json.dumps(
            metrics, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if (
            len(metrics) > MAX_COMPILER_METRIC_FIELDS
            or len(encoded) > MAX_COMPILER_METRICS_BYTES
        ):
            counts["invalid_envelope_count"] += 1
            add("compiler_metrics_unbounded", event)
        claimed_runtime = any(
            isinstance(metrics.get(field), int) and metrics.get(field, 0) > 0
            for field in RUNTIME_USAGE_FIELDS
        )
        if claimed_runtime and metrics.get("usage_aggregate_eligible") is not True:
            counts["unattested_runtime_claim_count"] += 1
            add("runtime_usage_unattested", event)

    return {
        "status": "warn" if findings else "pass",
        **counts,
        "finding_count": (
            counts["invalid_envelope_count"]
            + counts["historical_v2_read_only_debt_count"]
            + counts["unattested_runtime_claim_count"]
        ),
        "findings_truncated": (
            counts["invalid_envelope_count"]
            + counts["historical_v2_read_only_debt_count"]
            + counts["unattested_runtime_claim_count"]
        )
        > len(findings),
        "findings": findings,
    }


__all__ = ["lint_compiler_contract"]
