"""Content-bound active-advice packet construction."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from typing import Any


NON_ACTIONABLE_STATES = {
    "deferred",
    "grouping_only",
    "not_applicable",
    "rejected",
    "retired",
}


def _true(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"true", "1", "yes"}


def _state(value: Any) -> str:
    return str(value or "").strip().lower()


def _actionable_child(record: dict[str, Any]) -> str | None:
    child = str(record.get("actionable_child") or "").strip()
    child_state = _state(record.get("actionable_child_consumption_state"))
    if (
        not child
        or child_state in NON_ACTIONABLE_STATES
        or child_state.startswith("deferred")
    ):
        return None
    return child


def clause_id_sets(item: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return declared owner IDs and currently actionable clause IDs."""

    fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
    directives = (
        fields.get("directives") if isinstance(fields.get("directives"), list) else []
    )
    declared: set[str] = set()
    actionable: set[str] = set()
    for record in directives:
        if not isinstance(record, dict):
            continue
        clause_id = str(record.get("directive_id") or "").strip()
        if not clause_id:
            continue
        declared.add(clause_id)
        child = _actionable_child(record)
        if child:
            actionable.add(child)
        state = _state(record.get("directive_state"))
        disposition = _state(record.get("selection_disposition"))
        if (
            _true(record.get("grouping_only"))
            or state in NON_ACTIONABLE_STATES
            or state.startswith("deferred")
            or disposition.startswith("deferred")
        ):
            continue
        actionable.add(clause_id)
    return sorted(declared), sorted(actionable)


def _binding_item(item: dict[str, Any]) -> dict[str, Any]:
    declared, actionable = clause_id_sets(item)
    return {
        "advice_id": str(item.get("advice_id") or ""),
        "source_digest": str(item.get("raw_sha256") or "").lower(),
        "normalized_content_digest": str(item.get("content_sha256") or "").lower(),
        "canonical_clause_ids": declared,
        "actionable_clause_ids": actionable,
    }


def advice_packet_digest_binding(items: list[dict[str, Any]]) -> dict[str, Any]:
    binding_items = sorted(
        (_binding_item(item) for item in items), key=lambda row: row["advice_id"]
    )
    return {
        "advice_packet_schema_version": 1,
        "applicability": (
            "applicable"
            if any(row["actionable_clause_ids"] for row in binding_items)
            else "not_applicable"
        ),
        "active_items": binding_items,
    }


def digest_binding(binding: dict[str, Any]) -> str:
    raw = json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def packet_identity_fields(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the exact expected-clause and source binding for consumers."""

    binding = advice_packet_digest_binding(items)
    declared: set[str] = set()
    actionable: set[str] = set()
    occurrences: Counter[str] = Counter()
    clause_sources: dict[str, set[str]] = defaultdict(set)
    source_digests: dict[str, str] = {}
    for item in binding["active_items"]:
        declared.update(item["canonical_clause_ids"])
        actionable.update(item["actionable_clause_ids"])
        source_digest = item["source_digest"]
        source_digests[item["advice_id"]] = source_digest
        for clause_id in item["actionable_clause_ids"]:
            occurrences[clause_id] += 1
            clause_sources[clause_id].add(source_digest)
    return {
        "advice_packet_schema_version": 1,
        "applicability": binding["applicability"],
        "canonical_clause_ids": sorted(declared),
        "actionable_clause_ids": sorted(actionable),
        "canonical_actionable_clause_ids": sorted(actionable),
        "source_digests": source_digests,
        "clause_source_digests": {
            clause_id: next(iter(digests))
            for clause_id, digests in sorted(clause_sources.items())
            if len(digests) == 1
        },
        "duplicate_actionable_clause_ids": sorted(
            clause_id for clause_id, count in occurrences.items() if count > 1
        ),
        "advice_packet_digest_basis": binding,
        "advice_packet_digest": digest_binding(binding),
    }


def enrich_item(item: dict[str, Any]) -> dict[str, Any]:
    declared, actionable = clause_id_sets(item)
    return {
        **item,
        "source_digest": str(item.get("raw_sha256") or "").lower(),
        "canonical_clause_ids": declared,
        "actionable_clause_ids": actionable,
        "canonical_actionable_clause_ids": actionable,
    }


__all__ = (
    "advice_packet_digest_binding",
    "clause_id_sets",
    "digest_binding",
    "enrich_item",
    "packet_identity_fields",
)
