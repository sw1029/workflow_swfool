"""Compiler-first full-inventory scan preparation and one-batch application."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from .contracts import NON_ACTIVE_STATUSES, PREFIXES
from .events import load_events_read_only, merge_state, path_records
from .render import _markdown_projection_matches
from .scan_service import (
    _artifact_update,
    _legacy_pack_render_corrections,
    _prepare_scan,
)
from .scan_integrity import preflight_scan_apply, validate_committed_snapshots, validate_scan_compilation
from .scan_result_integrity import load_existing_scan_result
from . import scan_projection_repair
from .artifacts import discover_standard_artifacts
from .storage import (
    atomic_write_bytes,
    immutable_snapshot_path,
    jsonl_path,
    markdown_path,
    rel_path,
    sha256_file,
    slugify,
)
from .transition_plan import (
    apply_transition_plan,
    build_transition_plan,
    publish_transition_plan,
)
from .transition_plan_contract import (
    canonical_bytes,
    owned_transition_file,
    publish_immutable,
    regular_payload,
    sha256_bytes,
    workspace_path,
)
from .transition_recovery import event_payload
COMPILATION_FIELDS = frozenset("""schema_version result_kind compilation_id
created_at effect_mode index_revision projection_revision inventory
logical_update_count event_count focus_results request request_sha256 plan_binding
snapshot_materializations compilation_sha256""".split())

def _fixed_timestamp(value: str) -> tuple[str, dt.datetime]:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--at must be a timezone-aware RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("--at must be a timezone-aware RFC3339 timestamp")
    return value, parsed

def _inventory(root: Path) -> tuple[list[tuple[str, str, str, str]], dict[str, Any]]:
    artifacts = discover_standard_artifacts(root)
    rows = [
        {
            "type": item_type,
            "ref": path_value,
            "status": status,
            "title": title,
            "sha256": sha256_file(workspace_path(root, path_value)),
        }
        for item_type, path_value, status, title in artifacts
    ]
    return artifacts, {"artifact_count": len(rows), "items": rows,
                       "sha256": sha256_bytes(canonical_bytes(rows))}

def _allocate_id(
    item_type: str, title: str, parsed: dt.datetime, occupied: set[str]
) -> str:
    prefix = PREFIXES.get(item_type, slugify(item_type, "item"))
    base = (
        f"{prefix}-{parsed.strftime('%Y%m%d-%H%M%S')}-"
        f"{slugify(title, item_type)}"
    )
    candidate, suffix = base, 2
    while candidate in occupied:
        candidate = f"{base}-{suffix}"
        suffix += 1
    occupied.add(candidate)
    return candidate

def _focus_results(
    inventory: dict[str, Any], focus: dict[str, str] | None
) -> list[dict[str, Any]]:
    if focus is None:
        return []
    matches = [row for row in inventory["items"] if row["ref"] == focus["ref"]]
    if not matches:
        return [{**focus, "status": "not_discovered", "artifact_type": None}]
    if len(matches) != 1 or matches[0]["sha256"] != focus["sha256"]:
        raise ValueError("Focused scan source differs from its exact binding")
    row = matches[0]
    return [{**focus, "status": row["status"], "artifact_type": row["type"],
             "title": row["title"]}]

def _snapshot_fields(
    root: Path, item_id: str, path_value: str, digest: str | None
) -> tuple[dict[str, str], dict[str, str]]:
    source = workspace_path(root, path_value)
    snapshot = immutable_snapshot_path(root, item_id, source)
    binding = {
        "source_ref": path_value,
        "source_sha256": str(digest or ""),
        "target_ref": rel_path(root, snapshot),
    }
    fields = {"record_class": "mutable_alias", "snapshot_digest": str(digest or ""),
              "snapshot_path": binding["target_ref"], "canonical_id": item_id,
              "alias_path": path_value}
    return fields, binding

def _compile_events(
    root: Path,
    artifacts: list[tuple[str, str, str, str]],
    *,
    at: str,
    parsed: dt.datetime,
) -> tuple[list[dict[str, Any]], int, list[dict[str, str]]]:
    scan = _prepare_scan(root, artifacts, dry_run=True, now_fn=lambda: at)
    existing, _ = load_events_read_only(root)
    projected_events = list(existing)
    occupied = set(scan.projected_state)
    events: list[dict[str, Any]] = []
    snapshots: list[dict[str, str]] = []
    logical_updates = 0

    def append(rows: list[dict[str, Any]]) -> None:
        nonlocal projected_events
        for row in rows:
            row.setdefault("updated_at", at)
        events.extend(rows)
        projected_events.extend(rows)
        scan.projected_state = merge_state(projected_events)

    for correction in _legacy_pack_render_corrections(scan):
        append([{
            "event": "upsert",
            "id": correction.item_id,
            "type": "task_pack",
            "status": "superseded",
            "path": correction.path_value,
            "title": correction.title,
            "content_sha256": correction.digest,
            "fields": correction.fields,
            "note": correction.reason,
        }])
        logical_updates += 1

    for artifact in artifacts:
        update = _artifact_update(scan, artifact)
        if update is None:
            continue
        item_id = update.item_id or _allocate_id(
            update.item_type, update.title, parsed, occupied
        )
        records = [
            row
            for row in path_records(
                scan.projected_state, update.item_type, update.path_value,
                active_only=True,
            )
            if row[0] != item_id
        ]
        for alias_id in update.retire_alias_ids:
            alias = scan.projected_state.get(alias_id)
            if (
                alias_id != item_id
                and isinstance(alias, dict)
                and alias.get("status") not in NON_ACTIVE_STATUSES
                and all(row_id != alias_id for row_id, _ in records)
            ):
                records.append((alias_id, alias))
        outgoing: list[dict[str, Any]] = []
        for previous_id, _previous in sorted(records):
            outgoing.extend([
                {"event": "upsert", "id": previous_id, "status": "superseded"},
                {
                    "event": "link", "id": previous_id,
                    "links": [{"rel": "superseded_by", "id": item_id}],
                },
            ])
        fields = dict(update.fields or {})
        if update.item_type == "task" and update.path_value == "task.md":
            task_fields, materialization = _snapshot_fields(
                root, item_id, update.path_value, update.digest
            )
            fields.update(task_fields)
            snapshots.append(materialization)
        current: dict[str, Any] = {
            "event": "upsert", "id": item_id, "type": update.item_type,
            "status": update.status, "path": update.path_value,
            "title": update.title, "content_sha256": update.digest}
        if item_id not in scan.projected_state:
            current["created_at"] = at
        if records:
            current["links"] = [
                {"rel": "supersedes", "id": prior_id}
                for prior_id, _prior in sorted(records)
            ]
        if fields:
            current["fields"] = fields
        outgoing.append(current)
        append(outgoing)
        logical_updates += 1
    return events, logical_updates, snapshots

def prepare_scan(
    root: Path,
    *,
    at: str,
    focus: dict[str, str] | None = None,
    publish: bool = True,
) -> dict[str, Any]:
    """Compile the complete inventory once and optionally publish immutable metadata."""
    root = root.resolve()
    timestamp, parsed = _fixed_timestamp(at)
    if focus is not None:
        focus = _normalize_binding(focus, "scan focus")
    artifacts, inventory = _inventory(root)
    events, logical_count, snapshots = _compile_events(
        root, artifacts, at=timestamp, parsed=parsed
    )
    existing, index_digest = load_events_read_only(root)
    projection_current = _markdown_projection_matches(root, merge_state(existing))
    projection_digest = sha256_file(markdown_path(root))
    effect_mode = (
        "event_batch" if events else "no_effect" if projection_current else "projection_repair"
    )
    request = (
        {"schema_version": 1, "updated_at": timestamp, "render": True, "events": events}
        if events else None
    )
    plan = build_transition_plan(root, request, at=timestamp) if request else None
    plan_binding = (
        {
            "ref": f".task/transition_plans/{plan['plan_id']}.json",
            "sha256": sha256_bytes(canonical_bytes(plan) + b"\n"),
        }
        if plan else None
    )
    identity = {
        "created_at": timestamp,
        "effect_mode": effect_mode,
        "inventory_sha256": inventory["sha256"],
        "index_sha256": index_digest,
        "projection_sha256": projection_digest,
        "request_sha256": sha256_bytes(canonical_bytes(request)),
    }
    compilation_id = "scan-" + sha256_bytes(canonical_bytes(identity))[:32]
    body = {
        "schema_version": 1,
        "result_kind": "task_state_index_scan_compilation",
        "compilation_id": compilation_id,
        "created_at": timestamp,
        "effect_mode": effect_mode,
        "index_revision": {"ref": ".task/index.jsonl", "sha256": index_digest},
        "projection_revision": {"ref": ".task/index.md", "sha256": projection_digest},
        "inventory": inventory,
        "logical_update_count": logical_count,
        "event_count": len(events),
        "focus_results": _focus_results(inventory, focus),
        "request": request,
        "request_sha256": sha256_bytes(canonical_bytes(request)),
        "plan_binding": plan_binding,
        "snapshot_materializations": snapshots,
    }
    compilation = {**body, "compilation_sha256": sha256_bytes(canonical_bytes(body))}
    created = False
    if publish:
        if plan is not None:
            planned = publish_transition_plan(root, plan)
            if planned["plan_file_sha256"] != plan_binding["sha256"]:
                raise ValueError("Published scan plan differs from its compilation")
            created = created or bool(planned["mutation_performed"])
        path = owned_transition_file(
            root, "scan_compilations", f"{compilation_id}.json", create_parent=True
        )
        created = publish_immutable(path, canonical_bytes(compilation) + b"\n") or created
        compilation_binding = {"ref": rel_path(root, path), "sha256": sha256_file(path)}
    else:
        compilation_binding = {"ref": None, "sha256": None}
    return {
        "result_kind": "task_state_index_scan_prepare_result",
        "schema_version": 1,
        "status": "prepared" if publish and created else "already_prepared" if publish else "dry_run",
        "effect_mode": effect_mode,
        "compilation_id": compilation_id,
        "compilation_binding": compilation_binding,
        "plan_binding": plan_binding,
        "logical_update_count": logical_count,
        "event_count": len(events),
        "focus_results": compilation["focus_results"],
        "would_change": effect_mode != "no_effect",
        "mutation_performed": created,
        "compilation": compilation if not publish else None,
    }

def _normalize_binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise ValueError(f"{label} requires exactly ref and sha256")
    ref, digest = value.get("ref"), value.get("sha256")
    if (
        not isinstance(ref, str) or not ref or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{label} binding is invalid")
    return {"ref": ref, "sha256": digest}

def load_scan_compilation(
    root: Path, value: dict[str, str]
) -> tuple[dict[str, str], dict[str, Any]]:
    binding = _normalize_binding(value, "scan compilation")
    path = workspace_path(root, binding["ref"])
    relative = path.relative_to(root.resolve())
    if relative.parts[:2] != (".task", "scan_compilations") or len(relative.parts) != 3:
        raise ValueError("Scan compilation path is not canonical")
    payload = regular_payload(path)
    if sha256_bytes(payload) != binding["sha256"]:
        raise ValueError("Scan compilation bytes differ from their binding")
    try:
        compilation = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Scan compilation is not JSON") from exc
    if not isinstance(compilation, dict) or set(compilation) != COMPILATION_FIELDS:
        raise ValueError("Scan compilation fields are not closed")
    body = {key: value for key, value in compilation.items()
            if key != "compilation_sha256"}
    if (
        compilation.get("schema_version") != 1
        or compilation.get("result_kind") != "task_state_index_scan_compilation"
        or compilation.get("compilation_sha256") != sha256_bytes(canonical_bytes(body))
        or relative.name != f"{compilation.get('compilation_id')}.json"
        or payload != canonical_bytes(compilation) + b"\n"
    ):
        raise ValueError("Scan compilation integrity check failed")
    validate_scan_compilation(compilation)
    return binding, compilation

def _materialize_snapshots(root: Path, rows: list[dict[str, str]]) -> None:
    for row in rows:
        source = workspace_path(root, row["source_ref"])
        target = workspace_path(root, row["target_ref"])
        payload = regular_payload(source)
        if sha256_bytes(payload) != row["source_sha256"]:
            raise ValueError("Scan snapshot source changed; recompile_required")
        if target.exists() or target.is_symlink():
            if regular_payload(target) != payload:
                raise ValueError("Scan snapshot target conflicts with exact source")
            continue
        atomic_write_bytes(target, payload)

def _publish_scan_result(root: Path, result: dict[str, Any]) -> dict[str, Any]:
    sealed = {**result, "result_sha256": sha256_bytes(canonical_bytes(result))}
    path = owned_transition_file(
        root, "scan_receipts", f"{result['compilation']['ref'].split('/')[-1]}",
        create_parent=True,
    )
    created = publish_immutable(path, canonical_bytes(sealed) + b"\n")
    digest = sha256_file(path)
    return {
        "result_kind": "task_state_index_scan_apply_result",
        "schema_version": 2,
        "status": "applied" if created else "already_applied",
        "effect_status": sealed["effect_status"],
        "logical_update_count": sealed["logical_update_count"],
        "event_count": sealed["event_batch"]["event_count"],
        "focus_results": sealed["focus_results"],
        "owner_result_binding": {"ref": rel_path(root, path), "sha256": digest},
        "mutation_performed": bool(created or sealed["effect_status"] == "confirmed_effect"),
    }

def apply_scan(root: Path, compilation_value: dict[str, str]) -> dict[str, Any]:
    """Apply one published scan compilation through one transition batch/render."""
    root = root.resolve()
    binding, compilation = load_scan_compilation(root, compilation_value)
    receipt_path = owned_transition_file(
        root, "scan_receipts", f"{compilation['compilation_id']}.json",
        create_parent=False,
    )
    prior = load_existing_scan_result(
        root, receipt_path, binding, compilation
    )
    if prior is not None:
        payload = regular_payload(receipt_path)
        return {
            "result_kind": "task_state_index_scan_apply_result", "schema_version": 2,
            "status": "already_applied",
            "effect_status": prior["effect_status"],
            "logical_update_count": prior["logical_update_count"],
            "event_count": prior["event_batch"]["event_count"],
            "focus_results": prior["focus_results"],
            "owner_result_binding": {
                "ref": rel_path(root, receipt_path), "sha256": sha256_bytes(payload)
            },
            "mutation_performed": False,
        }
    _events, current_index = load_events_read_only(root)
    repair_intent = None
    repair_started = False
    if compilation["effect_mode"] == "projection_repair":
        repair_intent, repair_started = scan_projection_repair.inspect_projection_repair(
            root, binding, compilation, _events
        )
    plan, committed = preflight_scan_apply(
        root,
        compilation,
        _events,
        current_index,
        projection_repair_started=repair_started,
    )
    if committed:
        validate_committed_snapshots(root, compilation["snapshot_materializations"])
    else:
        _artifacts, current_inventory = _inventory(root)
        if current_inventory["sha256"] != compilation["inventory"]["sha256"]:
            raise ValueError("Scan compilation prestate changed; recompile_required")
        _materialize_snapshots(root, compilation["snapshot_materializations"])
    transition_receipt = None
    if compilation["effect_mode"] == "event_batch":
        transition = apply_transition_plan(root, compilation["plan_binding"]["ref"])
        transition_receipt = transition["execution_result_binding"]
        before_subject = plan["ledger"]["before_sha256"]
        after_subject = plan["ledger"]["after_sha256"]
        before_projection = plan["markdown"]["before_sha256"]
        after_projection = plan["markdown"]["after_sha256"]
        batch = {
            "plan_id": plan["plan_id"],
            "before_event_count": plan["ledger"]["before_event_count"],
            "event_count": plan["ledger"]["event_count"],
            "event_payload_sha256": sha256_bytes(event_payload(plan["events"])),
        }
    else:
        before_subject = compilation["index_revision"]["sha256"] or sha256_bytes(b"")
        before_projection = compilation["projection_revision"]["sha256"]
        if compilation["effect_mode"] == "projection_repair":
            if repair_intent is None:
                raise ValueError("Projection repair intent is missing")
            transition_receipt = scan_projection_repair.apply_or_recover_projection_repair(
                root, binding, compilation, _events, repair_intent,
                already_applied=committed,
            )
        after_subject = sha256_file(jsonl_path(root)) or sha256_bytes(b"")
        after_projection = sha256_file(markdown_path(root))
        batch = {
            "plan_id": compilation["compilation_id"], "before_event_count": len(_events),
            "event_count": 0, "event_payload_sha256": sha256_bytes(b""),
        }
    post = prepare_scan(
        root, at=compilation["created_at"], publish=False,
        focus=(
            {key: compilation["focus_results"][0][key] for key in ("ref", "sha256")}
            if compilation["focus_results"] else None
        ),
    )
    effect = (
        "confirmed_no_effect"
        if compilation["effect_mode"] == "no_effect"
        else "confirmed_effect"
    )
    result = {
        "schema_version": 2,
        "artifact_kind": "task_state_index_scan_result",
        "operation": "scan",
        "effect_status": effect,
        "completed_at": compilation["created_at"],
        "compilation": binding,
        "plan": compilation["plan_binding"],
        "transition_receipt": transition_receipt,
        "subject": {
            "kind": "task_index", "ref": ".task/index.jsonl",
            "before_sha256": before_subject, "after_sha256": after_subject,
        },
        "projection": {
            "ref": ".task/index.md", "before_sha256": before_projection,
            "after_sha256": after_projection,
        },
        "logical_update_count": compilation["logical_update_count"],
        "event_batch": batch,
        "focus_results": compilation["focus_results"],
        "post_check": {
            "would_change": post["would_change"],
            "logical_update_count": post["logical_update_count"],
            "event_count": post["event_count"],
            "inventory_sha256": post["compilation"]["inventory"]["sha256"],
        },
    }
    return _publish_scan_result(root, result)


__all__ = (
    "apply_scan", "load_scan_compilation", "prepare_scan",
)
