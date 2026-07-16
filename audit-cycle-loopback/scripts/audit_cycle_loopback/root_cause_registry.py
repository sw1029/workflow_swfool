from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT
from . import root_cause as _root_cause
from . import values as _values

def compact_root_cause_ledger(rows: list[dict[str, Any]], max_rows_per_family: int) -> list[dict[str, Any]]:
    lineage_rows: list[dict[str, Any]] = []
    prior_by_attempt: dict[str, list[dict[str, Any]]] = {}
    label_fields = (
        "family_key",
        "root_key",
        "root_family_key",
        "hypothesized_root_cause",
    )
    for supplied in rows:
        row = dict(supplied)
        attempt_identity = str(row.get("attempt_identity") or "")
        prior = next(
            (
                candidate
                for candidate in reversed(prior_by_attempt.get(attempt_identity, []))
                if attempt_identity and _root_cause.equivalent_root_cause(row, candidate)
            ),
            None,
        )
        if prior is not None:
            labels_changed = any(
                str(prior.get(field) or "") != str(row.get(field) or "")
                for field in label_fields
            )
            if not labels_changed:
                continue
            row["label_correction"] = True
            row["correction_of_attempt_identity"] = attempt_identity
            row["repair_attempted"] = False
            row["attempt_count"] = 0
            row["vacuous_attempt_count"] = 0
        lineage_rows.append(row)
        if attempt_identity:
            prior_by_attempt.setdefault(attempt_identity, []).append(row)

    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in lineage_rows:
        family = str(row.get("family_key") or "unknown")
        buckets.setdefault(family, []).append(row)
    compacted: list[dict[str, Any]] = []
    for family_rows in buckets.values():
        latest_by_equivalence: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in family_rows:
            key = _root_cause.root_cause_distinct_key(row)
            existing = latest_by_equivalence.get(key)
            merged = dict(row)
            label_correction = _values.bool_value(row.get("label_correction"))
            attempted_increment = 1 if _values.bool_value(row.get("repair_attempted")) and not label_correction else 0
            vacuous_increment = attempted_increment if not _values.bool_value(row.get("terminal_outcome_changed")) else 0
            if existing:
                merged["attempt_count"] = _root_cause.root_cause_attempt_weight(existing, "attempt_count") + attempted_increment
                merged["vacuous_attempt_count"] = _root_cause.root_cause_attempt_weight(existing, "vacuous_attempt_count") + vacuous_increment
                merged["terminal_outcome_changed"] = _values.bool_value(existing.get("terminal_outcome_changed")) or _values.bool_value(row.get("terminal_outcome_changed"))
                merged["first_cycle_id"] = existing.get("first_cycle_id") or existing.get("cycle_id")
                merged["previous_cycle_id"] = existing.get("cycle_id")
                if label_correction:
                    merged["repair_attempted"] = _values.bool_value(existing.get("repair_attempted"))
                aliases = set(_values.list_values(existing.get("hypothesis_aliases")))
                aliases.add(str(existing.get("hypothesized_root_cause") or ""))
                aliases.add(str(row.get("hypothesized_root_cause") or ""))
                merged["hypothesis_aliases"] = sorted(alias for alias in aliases if alias)[:20]
            else:
                merged["attempt_count"] = _root_cause.root_cause_attempt_weight(row, "attempt_count", attempted_increment)
                merged["vacuous_attempt_count"] = _root_cause.root_cause_attempt_weight(row, "vacuous_attempt_count", vacuous_increment)
            latest_by_equivalence[key] = merged
        compacted.extend(list(latest_by_equivalence.values())[-max_rows_per_family:])
    return compacted

def append_root_cause_ledger(path: Path, entries: list[dict[str, Any]], max_rows_per_family: int = ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT) -> tuple[list[dict[str, Any]], bool]:
    """Reject the retired append-and-write helper rather than publish partial truth."""
    raise RuntimeError(
        "direct root-cause ledger writes are prohibited; prepare the root_cause_ledger typed operation instead"
    )

def feed_exhausted_family_seal(root: Path, packet: dict[str, Any]) -> str | None:
    """Reject the retired seal writer; the finalizer publishes its projection atomically."""
    raise RuntimeError(
        "direct family-seal writes are prohibited; prepare the sealed_blocker_families typed operation instead"
    )

def project_exhausted_family_seal(existing: Any, packet: dict[str, Any]) -> dict[str, Any]:
    """Project a complete seal state without publishing it."""
    if isinstance(existing, dict) and isinstance(existing.get("families"), list):
        data = dict(existing)
        records = [item for item in existing["families"] if isinstance(item, dict)]
    elif isinstance(existing, list):
        data = {"schema_version": "sealed-blocker-families-v1", "families": [item for item in existing if isinstance(item, dict)]}
        records = data["families"]
    elif isinstance(existing, dict):
        records = [existing]
        data = {"schema_version": "sealed-blocker-families-v1", "families": records}
    else:
        data = {"schema_version": "sealed-blocker-families-v1", "families": []}
        records = data["families"]
    semantic = str(packet.get("semantic_signature") or "").lower()
    blocker = str(packet.get("blocker_signature") or "").lower()
    root_family = str(packet.get("root_family_key") or packet.get("blocker_root_family") or "").lower()
    record = exhausted_family_seal_record(packet)
    replaced = False
    for index, item in enumerate(records):
        if (
            str(item.get("semantic_signature") or "").lower() == semantic
            and str(item.get("blocker_signature") or "").lower() == blocker
            and str(item.get("root_family_key") or "").lower() == root_family
        ):
            records[index] = {**item, **record}
            replaced = True
            break
    if not replaced:
        records.append(record)
    data["families"] = records[-200:]
    return data

def exhausted_family_seal_record(packet: dict[str, Any]) -> dict[str, Any]:
    """Build a seal mutation payload without writing workflow state."""
    semantic = str(packet.get("semantic_signature") or "").lower()
    blocker = str(packet.get("blocker_signature") or "").lower()
    root_family = str(packet.get("root_family_key") or packet.get("blocker_root_family") or "").lower()
    root_key = str(packet.get("root_key") or "").lower()
    return {
        "semantic_signature": semantic or None,
        "blocker_signature": blocker or None,
        "root_key": root_key or None,
        "root_family_key": root_family or None,
        "hypothesis_exhausted": True,
        "vacuous_untried_attempt_count": packet.get("vacuous_untried_attempt_count"),
        "untried_promotion_budget": packet.get("untried_promotion_budget"),
        "reason": "root-cause hypothesis budget exhausted without terminal_outcome_changed",
        "source": "audit-cycle-loopback",
    }
