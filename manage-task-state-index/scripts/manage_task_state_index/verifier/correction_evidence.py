"""Independent correction, quarantine, manifest, and anchor reconstruction."""

from __future__ import annotations

from typing import Any

from .core import (
    ANCHOR_KIND,
    MIGRATION_EVENT_FIELD,
    NON_ACTIVE_STATUSES,
    _broken_links,
    _canonical_json,
    _merge_state,
    _require,
    _sha256,
    _versioned,
)


def _make_corrections(
    events: list[dict[str, Any]],
    mapping: dict[str, Any],
    transaction_id: str,
    task_anchor: dict[str, str],
    pack_anchor: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    effective_at = mapping["effective_at"]
    task_id, pack_id = task_anchor["id"], pack_anchor["id"]
    task_path, pack_path = task_anchor["path"], pack_anchor["path"]
    state = _merge_state(events)
    corrections: list[dict[str, Any]] = []
    superseded_tasks: list[str] = []
    superseded_packs: list[str] = []
    before_tasks = sorted(
        item_id for item_id, item in state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    )
    before_packs = sorted(
        item_id for item_id, item in state.items()
        if item.get("type") == "task_pack" and item.get("status") == "active"
    )
    before_aliases = sorted(
        item_id for item_id, item in state.items()
        if item_id != task_id
        and item.get("type") == "task"
        and item.get("path") == task_path
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    before_broken = [
        {"source_id": item_id, "rel": link["rel"], "id": link["id"]}
        for item_id in before_tasks
        for link in state.get(item_id, {}).get("links", [])
        if isinstance(link, dict) and link.get("id") not in state
    ]
    for item_id, item in sorted(state.items()):
        if item_id == task_id or item.get("type") != "task":
            continue
        if item.get("status") == "active" or (
            item.get("path") == task_path and item.get("status") not in NON_ACTIVE_STATUSES
        ):
            corrections.append(_versioned({
                "event": "upsert", "id": item_id, "type": "task", "status": "superseded",
                "path": str(item.get("path") or task_path), "title": str(item.get("title") or item_id),
                "updated_at": effective_at,
                "fields": {"migration_id": transaction_id, "superseded_by": task_id},
            }))
            superseded_tasks.append(item_id)
    for item_id, item in sorted(state.items()):
        if item_id == pack_id or item.get("type") != "task_pack":
            continue
        if item.get("status") == "active":
            corrections.append(_versioned({
                "event": "upsert", "id": item_id, "type": "task_pack", "status": "superseded",
                "path": str(item.get("path") or ".task/task_pack"), "title": str(item.get("title") or item_id),
                "updated_at": effective_at,
                "fields": {"migration_id": transaction_id, "superseded_by": pack_id},
            }))
            superseded_packs.append(item_id)
    current_links = state.get(task_id, {}).get("links", [])
    tombstones = [
        {"rel": link["rel"], "id": link["id"]}
        for link in current_links
        if isinstance(link, dict) and (
            link.get("id") not in state
            or link.get("rel") == "promoted_from_pack"
            or (link.get("rel") == "pack_for_task" and link.get("id") != pack_id)
        )
    ]
    corrections.append(_versioned({
        "event": "upsert", "id": task_id, "type": "task", "status": "active",
        "path": task_path, "title": str(state.get(task_id, {}).get("title") or task_id),
        "content_sha256": task_anchor["sha256"], "updated_at": effective_at,
        "fields": {"record_class": "mutable_alias", "canonical_id": task_id,
                   "projection_epoch": transaction_id, "link_tombstones": tombstones},
        "links": [{"rel": "pack_for_task", "id": pack_id}],
    }))
    corrections.append(_versioned({
        "event": "upsert", "id": pack_id, "type": "task_pack", "status": "active",
        "path": pack_path, "title": str(state.get(pack_id, {}).get("title") or pack_id),
        "content_sha256": pack_anchor["sha256"], "updated_at": effective_at,
        "fields": {"pack_id": pack_id, "projection_epoch": transaction_id,
                   "planning_relationship": "non_promotion"},
        "links": [{"rel": "pack_for_task", "id": task_id}],
    }))
    for ordinal, event in enumerate(corrections, start=1):
        fields = dict(event.get("fields") or {})
        fields["migration_correction_event_id"] = f"{transaction_id}-correction-{ordinal:06d}"
        event["fields"] = fields
    final = _merge_state(events + corrections)
    active_tasks = sorted(item_id for item_id, item in final.items() if item.get("type") == "task" and item.get("status") == "active")
    active_packs = sorted(item_id for item_id, item in final.items() if item.get("type") == "task_pack" and item.get("status") == "active")
    aliases = sorted(
        item_id for item_id, item in final.items()
        if item_id != task_id and item.get("type") == "task" and item.get("path") == task_path
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    broken = _broken_links(final, task_id)
    projection = {
        "before_active_task_ids": before_tasks,
        "before_active_task_count": len(before_tasks),
        "before_active_pack_ids": before_packs,
        "before_active_pack_count": len(before_packs),
        "before_duplicate_active_alias_ids": before_aliases,
        "before_duplicate_active_alias_count": len(before_aliases),
        "before_current_broken_links": before_broken,
        "before_current_broken_link_count": len(before_broken),
        "active_task_ids": active_tasks,
        "active_task_count": len(active_tasks),
        "active_pack_ids": active_packs,
        "active_pack_count": len(active_packs),
        "duplicate_active_alias_ids": aliases,
        "duplicate_active_alias_count": len(aliases),
        "current_broken_links": broken,
        "current_broken_link_count": len(broken),
        "current_active_pack_indexed": pack_id in final,
        "current_projection_status": "evaluated",
        "projection_completeness": "complete",
        "current_surface_blocker_count": int(active_tasks != [task_id]) + int(active_packs != [pack_id]) + len(aliases) + len(broken),
        "superseded_task_ids": superseded_tasks,
        "superseded_pack_ids": superseded_packs,
        "retracted_links": tombstones,
    }
    return corrections, projection

def _correction_identity(event: dict[str, Any]) -> tuple[str, str]:
    fields = event.get("fields") if isinstance(event.get("fields"), dict) else {}
    identity = fields.get("migration_correction_event_id")
    _require(isinstance(identity, str) and identity, "correction event identity is missing")
    return identity, _sha256(_canonical_json(event))

def _bind_quarantine_corrections(
    rows: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
    task_id: str,
    pack_id: str,
) -> None:
    indexed = [(event, *_correction_identity(event)) for event in corrections]
    _require(len({identity for _event, identity, _digest in indexed}) == len(indexed), "correction identities repeat")
    for row in rows:
        if row["classification"] != "quarantined_historical" or row["projection_impact"] == "independent":
            continue
        resolution, identity = row["resolution"], row["deterministic_identity"]
        candidates: list[tuple[dict[str, Any], str, str]] = []
        if resolution == "projection_epoch_reset":
            candidates = [item for item in indexed if item[0].get("id") in {task_id, pack_id}]
        elif resolution == "superseded_by_canonical_task":
            candidates = [item for item in indexed if item[0].get("id") == identity and item[0].get("type") == "task" and item[0].get("status") == "superseded"]
        elif resolution == "superseded_by_canonical_pack":
            candidates = [item for item in indexed if item[0].get("id") == identity and item[0].get("type") == "task_pack" and item[0].get("status") == "superseded"]
        elif resolution == "link_retracted":
            candidates = [item for item in indexed if item[0].get("id") == task_id and bool(item[0].get("fields", {}).get("link_tombstones"))]
        _require(bool(candidates), f"quarantine line {row['line']} lacks exact correction ownership")
        row["correction_event_ids"] = [item[1] for item in candidates]
        row["correction_event_sha256s"] = [item[2] for item in candidates]

def _validate_quarantine_bindings(rows: list[dict[str, Any]], corrections: list[dict[str, Any]]) -> None:
    graph = {identity: digest for event in corrections for identity, digest in [_correction_identity(event)]}
    _require(len(graph) == len(corrections), "correction graph repeats an identity")
    for row in rows:
        ids, digests = row.get("correction_event_ids"), row.get("correction_event_sha256s")
        _require(isinstance(ids, list) and isinstance(digests, list) and len(ids) == len(digests), "row correction binding shape is invalid")
        non_independent = row.get("classification") == "quarantined_historical" and row.get("projection_impact") != "independent"
        _require(not non_independent or bool(ids), "non-independent quarantine lacks a correction binding")
        _require(non_independent or not ids, "independent row carries a correction binding")
        _require(len(set(ids)) == len(ids), "row repeats a correction identity")
        for identity, digest in zip(ids, digests, strict=True):
            _require(graph.get(identity) == digest, "quarantine correction binding mismatch")

def _manifest(
    transaction_id: str,
    prefix: bytes,
    rows: list[dict[str, Any]],
    counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "kind": "task_state_index_resolution_manifest",
        "migration_id": transaction_id,
        "source_prefix_sha256": _sha256(prefix),
        "source_prefix_byte_length": len(prefix),
        "source_raw_row_count": len(rows),
        "classification_counts": counts,
        "rows": rows,
        "raw_row_bodies_included": False,
    }

def _anchor_event(
    plan: dict[str, Any], receipt_sha: str, journal_sha: str, marker_sha: str
) -> dict[str, Any]:
    return _versioned({
        "event": "upsert", "id": plan["receipt_anchor_id"], "type": "schema_contract",
        "status": "informational", "path": plan["receipt_ref"],
        "title": "Task state legacy migration seal", "updated_at": plan["effective_at"],
        "fields": {
            MIGRATION_EVENT_FIELD: ANCHOR_KIND,
            "migration_id": plan["migration_id"],
            "receipt_ref": plan["receipt_ref"],
            "receipt_sha256": receipt_sha,
            "seal_sha256": plan["seal"]["line_sha256"],
            "commit_boundary_sha256": plan["expected_after_index_sha256"],
            "journal_ref": plan["journal_ref"],
            "journal_sha256": journal_sha,
            "completion_marker_ref": plan["completion_marker_ref"],
            "completion_marker_sha256": marker_sha,
        },
    })
