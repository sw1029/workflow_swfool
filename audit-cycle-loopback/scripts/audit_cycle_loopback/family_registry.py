from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import values as _values
from .registry_identity import attempt_revision_value, logical_attempt_key

def load_registry(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []
    return rows

def compact_registry(rows: list[dict[str, Any]], max_rows_per_family: int) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    identity_index: dict[str, int] = {}
    for row in rows:
        identity = logical_attempt_key(row)
        if identity and identity in identity_index:
            index = identity_index[identity]
            previous = deduplicated[index]
            corrected = dict(previous)
            corrected.update(row)
            if any(
                str(previous.get(field) or "") != str(row.get(field) or "")
                for field in ("family_key", "root_key", "root_family_key", "blocker_signature")
            ):
                corrected["registry_label_correction"] = True
                corrected["correction_of_attempt_identity"] = str(
                    previous.get("attempt_identity") or row.get("attempt_identity") or ""
                )
                previous_revision = attempt_revision_value(previous)
                corrected.setdefault("attempt_revision_candidate", previous_revision + 1)
                corrected.setdefault("supersedes_attempt_revision_candidate", previous_revision)
                corrected.setdefault(
                    "supersedes_attempt_identity_candidate",
                    previous.get("attempt_identity"),
                )
            deduplicated[index] = corrected
            continue
        if identity:
            identity_index[identity] = len(deduplicated)
        deduplicated.append(row)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in deduplicated:
        buckets.setdefault(str(row.get("family_key") or "unknown"), []).append(row)
    compacted: list[dict[str, Any]] = []
    for family_rows in buckets.values():
        compacted.extend(family_rows[-max_rows_per_family:])
    return compacted

def write_registry(path: Path, rows: list[dict[str, Any]]) -> None:
    """Reject the retired direct-write path; finalization owns durable publication."""
    raise RuntimeError(
        "direct anti-loop registry writes are prohibited; publish a typed mutation candidate through cycle finalization"
    )

def normalize_hook_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", text)[:128]

def hook_demand_threshold_from_value(value: Any, default: Any = None) -> int | None:
    """Read an explicit hook-demand budget without supplying a global default."""
    parsed = _values.positive_int_or_none(value)
    if parsed is not None:
        return parsed
    return _values.positive_int_or_none(default)

def latest_adapter_hook_demand(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    for row in reversed(rows):
        raw = row.get("adapter_hook_demand")
        if not isinstance(raw, list):
            continue
        ledger: dict[str, dict[str, Any]] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            hook_id = normalize_hook_id(item.get("hook_id"))
            if not hook_id:
                continue
            affected_gate_ids = sorted(
                {
                    normalize_hook_id(gate_id)
                    for gate_id in _values.list_values(item.get("affected_gate_ids"))
                    if normalize_hook_id(gate_id)
                }
            )
            ledger[hook_id] = {
                "hook_id": hook_id,
                "skip_count": max(0, int(_values.float_value(item.get("skip_count")) or 0)),
                "decision_relevant_skip_count": max(
                    0,
                    int(_values.float_value(item.get("decision_relevant_skip_count")) or 0),
                ),
                "affected_gate_ids": affected_gate_ids,
                "first_skip_cycle_id": item.get("first_skip_cycle_id"),
                "last_skip_cycle_id": item.get("last_skip_cycle_id"),
            }
        return ledger
    return {}

def merge_adapter_hook_demand(
    rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    cycle_id: str,
) -> list[dict[str, Any]]:
    ledger = latest_adapter_hook_demand(rows)
    for event in events:
        if not isinstance(event, dict):
            continue
        hook_id = normalize_hook_id(event.get("hook_id"))
        if not hook_id:
            continue
        record = ledger.setdefault(
            hook_id,
            {
                "hook_id": hook_id,
                "skip_count": 0,
                "decision_relevant_skip_count": 0,
                "affected_gate_ids": [],
                "first_skip_cycle_id": cycle_id,
                "last_skip_cycle_id": cycle_id,
            },
        )
        record["skip_count"] = max(0, int(_values.float_value(record.get("skip_count")) or 0)) + 1
        if _values.bool_value(event.get("decision_relevant_skip")):
            record["decision_relevant_skip_count"] = (
                max(0, int(_values.float_value(record.get("decision_relevant_skip_count")) or 0)) + 1
            )
        affected = set(_values.list_values(record.get("affected_gate_ids")))
        gate_id = normalize_hook_id(event.get("affected_gate_id"))
        if gate_id:
            affected.add(gate_id)
        record["affected_gate_ids"] = sorted(affected)
        record["first_skip_cycle_id"] = record.get("first_skip_cycle_id") or cycle_id
        record["last_skip_cycle_id"] = cycle_id
    return [ledger[key] for key in sorted(ledger)]
