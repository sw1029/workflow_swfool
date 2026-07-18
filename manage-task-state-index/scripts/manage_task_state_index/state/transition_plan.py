"""Immutable plan/apply/verify support for bounded task-state event batches."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import (
    _append_events_unlocked,
    _load_events_unlocked,
    load_events_read_only,
    merge_state,
    versioned_event,
)
from .event_batch_validation import validate_event_batch
from .render import (
    _generated_at_from_markdown,
    _markdown_projection_matches,
    _rebuild_markdown_unlocked,
    _render_markdown_payload,
)
from .transition_no_effect import load_no_effect_receipt
from .storage import (
    index_lock,
    jsonl_path,
    markdown_path,
    now_iso,
    rel_path,
    sha256_file,
)
from .transition_plan_contract import (
    PLAN_KIND,
    PLAN_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    canonical_bytes as _canonical_bytes,
    canonical_plan_output_path,
    load_transition_plan,
    publish_immutable as _publish_immutable,
    receipt_for_plan as _receipt,
    receipt_status as _receipt_status,
    owned_transition_file,
    regular_payload as _regular_payload,
    sha256_bytes as _sha256_bytes,
    validate_transition_plan,
    workspace_path as _workspace_path,
)
from .transition_intent import (
    assert_no_pending_transition_intents,
    publish_transition_intent,
)
from .transition_recovery import (
    committed_boundary_valid as _committed_boundary_valid,
    event_payload as _event_payload,
    matching_events as _matching_events,
)
from .transition_semantics import validate_transition_plan_semantics
from .transition_verification import (
    cas_status as _cas_status,
    settle_transition_no_effect as _settle_transition_no_effect,
    verify_transition_plan_state,
)


def _read_ledger(root: Path) -> tuple[bytes, list[dict[str, Any]]]:
    path = _workspace_path(root, ".task/index.jsonl")
    payload = _regular_payload(path, missing=b"")
    events, _observed_digest = load_events_read_only(root)
    return payload, events


def _artifact_anchors(root: Path, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    final_upserts: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event") == "upsert" and event.get("path"):
            final_upserts[str(event["path"])] = event
    anchors: list[dict[str, Any]] = []
    for relative, event in sorted(final_upserts.items()):
        path = _workspace_path(root, relative)
        if path.exists() or path.is_symlink():
            _regular_payload(path)
        before_sha256 = sha256_file(path)
        planned_sha256 = event.get("content_sha256")
        if planned_sha256 is not None and (
            not isinstance(planned_sha256, str)
            or len(planned_sha256) != 64
            or any(character not in "0123456789abcdef" for character in planned_sha256)
        ):
            raise ValueError(
                f"Planned artifact content_sha256 must be lowercase SHA-256: {relative}"
            )
        expectation = (
            "planned_content_sha256"
            if isinstance(planned_sha256, str)
            else "unchanged_from_plan"
        )
        anchors.append(
            {
                "path": relative,
                "before_sha256": before_sha256,
                "expected_sha256": planned_sha256 or before_sha256,
                "expectation": expectation,
            }
        )
    return anchors


def _projected_markdown(
    root: Path,
    state: dict[str, dict[str, Any]],
    timestamp: str,
) -> tuple[str | None, bytes]:
    path = _workspace_path(root, ".task/index.md")
    before = _regular_payload(path, missing=b"")
    before_digest = _sha256_bytes(before) if before else None
    prior_generated = _generated_at_from_markdown(before)
    if prior_generated:
        candidate = _render_markdown_payload(state, prior_generated)
        if candidate == before:
            return before_digest, before
    return before_digest, _render_markdown_payload(state, timestamp)


def _validate_request(request: dict[str, Any]) -> list[dict[str, Any]]:
    from .transition_plan_contract import validate_transition_request

    return validate_transition_request(request)


def _validate_links(
    existing: list[dict[str, Any]], events: list[dict[str, Any]]
) -> None:
    final_state = merge_state([*existing, *events])
    known_ids = set(final_state)
    for event in events:
        if event.get("id") not in known_ids:
            raise ValueError(f"Transition event has unknown source id: {event.get('id')}")
        for link in event.get("links") or []:
            if link.get("id") not in known_ids:
                raise ValueError(f"Transition link target is not indexed: {link.get('id')}")


def _materialize_sparse_upsert(
    event: dict[str, Any], state: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if event.get("event") != "upsert" or all(
        isinstance(event.get(field), str) and event.get(field)
        for field in ("type", "status", "path")
    ):
        return event
    prior = state.get(str(event.get("id")))
    if not isinstance(prior, dict):
        raise ValueError("Sparse transition upsert references an unknown ID")
    materialized = dict(event)
    for field in (
        "type",
        "status",
        "path",
        "title",
        "parent_id",
        "content_sha256",
        "note",
    ):
        if field not in materialized and prior.get(field) is not None:
            materialized[field] = prior[field]
    return materialized


def build_transition_plan(
    root: Path,
    request: dict[str, Any],
    *,
    at: str | None = None,
) -> dict[str, Any]:
    """Build a zero-write, content-bound transition plan."""

    root = root.resolve()
    raw_events = _validate_request(request)
    ledger_payload, existing = _read_ledger(root)
    timestamp = str(request.get("updated_at") or at or now_iso())
    request_digest = _sha256_bytes(_canonical_bytes(request))
    identity_basis = {
        "request_sha256": request_digest,
        "ledger_sha256": _sha256_bytes(ledger_payload),
        "updated_at": timestamp,
    }
    plan_id = f"transition-{_sha256_bytes(_canonical_bytes(identity_basis))[:32]}"
    events: list[dict[str, Any]] = []
    projected_events = list(existing)
    for offset, raw_event in enumerate(raw_events, start=1):
        event = _materialize_sparse_upsert(
            dict(raw_event), merge_state(projected_events)
        )
        event.setdefault("updated_at", timestamp)
        if event["updated_at"] != timestamp:
            raise ValueError("All transition events must use the fixed plan timestamp")
        event["transition_plan_id"] = plan_id
        event = versioned_event(event)
        events.append(event)
        projected_events.append(event)
    _validate_links(existing, events)
    events = validate_event_batch(existing, events, source=jsonl_path(root))
    anchors = _artifact_anchors(root, events)
    after_ledger = ledger_payload
    if after_ledger and not after_ledger.endswith(b"\n"):
        after_ledger += b"\n"
    after_ledger += _event_payload(events)
    projected_state = merge_state([*existing, *events])
    markdown_before, markdown_after = _projected_markdown(
        root, projected_state, timestamp
    )
    body: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_kind": PLAN_KIND,
        "plan_id": plan_id,
        "created_at": timestamp,
        "request": request,
        "request_sha256": request_digest,
        "ledger": {
            "path": ".task/index.jsonl",
            "before_sha256": _sha256_bytes(ledger_payload),
            "after_sha256": _sha256_bytes(after_ledger),
            "before_size": len(ledger_payload),
            "before_event_count": len(existing),
            "before_events_sha256": _sha256_bytes(_canonical_bytes(existing)),
            "event_count": len(events),
        },
        "markdown": {
            "path": ".task/index.md",
            "before_sha256": markdown_before,
            "after_sha256": _sha256_bytes(markdown_after),
            "render": bool(request.get("render", True)),
        },
        "artifact_anchors": anchors,
        "events": events,
    }
    plan = {**body, "plan_sha256": _sha256_bytes(_canonical_bytes(body))}
    validate_transition_plan(plan)
    return plan


def publish_transition_plan(
    root: Path,
    plan: dict[str, Any],
    output: str | Path | None = None,
) -> dict[str, Any]:
    validate_transition_plan(plan)
    root = root.resolve()
    expected_output = f".task/transition_plans/{plan['plan_id']}.json"
    if output is not None and Path(output).as_posix() != expected_output:
        raise ValueError(
            "Task-state plan output must be an exact canonical plan-id path"
        )
    path = canonical_plan_output_path(
        root,
        expected_output,
    )
    payload = _canonical_bytes(plan) + b"\n"
    validate_transition_plan_semantics(root, plan)
    if not path.exists():
        planning_current, planning_defects = _cas_status(
            root, plan, phase="planning"
        )
        if not planning_current:
            raise ValueError(
                "Task-state transition plan planning CAS mismatch: "
                + ", ".join(planning_defects)
            )
    created = _publish_immutable(path, payload)
    return {
        "result_kind": "task_state_transition_plan_result",
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "planned" if created else "already_planned",
        "plan_id": plan["plan_id"],
        "plan_ref": rel_path(root, path),
        "plan_sha256": plan["plan_sha256"],
        "plan_content_sha256": _sha256_bytes(_canonical_bytes(plan)),
        "plan_file_sha256": _sha256_bytes(payload),
        "would_change": created,
        "mutation_performed": created,
        "plan": plan,
    }


def apply_transition_plan(root: Path, path_value: str | Path) -> dict[str, Any]:
    root = root.resolve()
    plan_path, plan, plan_file_sha256 = load_transition_plan(root, path_value)
    validate_transition_plan_semantics(root, plan)
    _workspace_path(root, ".task/index.jsonl")
    _workspace_path(root, ".task/index.md")
    plan_ref = rel_path(root, plan_path)
    preflight_no_effect, _preflight_receipt, _preflight_digest = (
        load_no_effect_receipt(root, plan, plan_ref, plan_file_sha256)
    )
    if preflight_no_effect == "current":
        raise ValueError("Task-state transition plan is settled with no effect")
    receipt_path = owned_transition_file(
        root,
        "transition_receipts",
        f"{plan['plan_id']}.json",
        create_parent=False,
    )
    replay = False
    recovered = False
    appended = False
    intent_created = False
    render_result: dict[str, Any] = {}
    with index_lock(root):
        assert_no_pending_transition_intents(
            root, allowed_plan_id=str(plan["plan_id"])
        )
        no_effect_status, _no_effect_receipt, _no_effect_digest = (
            load_no_effect_receipt(root, plan, plan_ref, plan_file_sha256)
        )
        if no_effect_status == "current":
            raise ValueError("Task-state transition plan is settled with no effect")
        existing, _ledger_digest = load_events_read_only(root)
        exact, conflict = _matching_events(existing, plan)
        if conflict:
            raise ValueError("Task-state transition plan is partially or conflictingly applied")
        if exact and not _committed_boundary_valid(root, plan, existing):
            raise ValueError("Task-state transition committed boundary is invalid")
        receipt = _receipt(plan, plan_ref, plan_file_sha256)
        receipt_status, receipt_file_sha256 = _receipt_status(receipt_path, receipt)
        if receipt_status == "conflict":
            raise ValueError("Task-state transition apply receipt conflict")
        if exact:
            replay = True
        else:
            current, defects = _cas_status(root, plan, phase="apply")
            if not current:
                raise ValueError("Task-state transition plan CAS mismatch: " + ", ".join(defects))
        if receipt_status == "missing":
            intent_created = publish_transition_intent(
                root, plan, plan_ref, plan_file_sha256
            )
        if not exact:
            _append_events_unlocked(
                root,
                plan["events"],
                allowed_transition_plan_id=str(plan["plan_id"]),
            )
            appended = True
        ledger_at_plan_boundary = (
            sha256_file(jsonl_path(root)) == plan["ledger"]["after_sha256"]
        )
        current_events = _load_events_unlocked(root)
        projection_current = (
            not plan["markdown"]["render"]
            or _markdown_projection_matches(root, merge_state(current_events))
        )
        repair_projection = bool(
            plan["markdown"]["render"]
            and (
                appended or receipt_status == "missing" or not projection_current
            )
        )
        if repair_projection:
            render_result = _rebuild_markdown_unlocked(
                root, now_fn=lambda: str(plan["created_at"])
            )
            if not _markdown_projection_matches(root, merge_state(current_events)):
                raise ValueError("Task-state transition current projection mismatch")
            if ledger_at_plan_boundary and sha256_file(markdown_path(root)) != plan[
                "markdown"
            ]["after_sha256"]:
                raise ValueError("Task-state transition rendered projection digest mismatch")
            recovered = replay
        if not ledger_at_plan_boundary and not replay:
            raise ValueError("Task-state transition ledger digest mismatch after apply")
        if receipt_status == "missing":
            receipt_path = owned_transition_file(
                root,
                "transition_receipts",
                f"{plan['plan_id']}.json",
                create_parent=True,
            )
            _publish_immutable(receipt_path, _canonical_bytes(receipt) + b"\n")
            receipt_file_sha256 = sha256_file(receipt_path)
            recovered = replay
        assert receipt_file_sha256 is not None
    return {
        "result_kind": "task_state_transition_apply_result",
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "already_applied" if replay else "applied",
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "receipt_ref": rel_path(root, receipt_path),
        "receipt_content_sha256": receipt["receipt_content_sha256"],
        "receipt_file_sha256": receipt_file_sha256,
        "execution_result_binding": {
            "ref": rel_path(root, receipt_path),
            "sha256": receipt_file_sha256,
        },
        "events_appended": 0 if replay else len(plan["events"]),
        "idempotent_replay": replay,
        "publication_recovered": recovered,
        "mutation_performed": appended or recovered or intent_created,
        "render_result": render_result,
    }


def verify_transition_plan(
    root: Path,
    path_value: str | Path,
    *,
    phase: str = "apply",
) -> dict[str, Any]:
    return verify_transition_plan_state(root, path_value, phase=phase)


def settle_transition_no_effect(
    root: Path,
    path_value: str | Path,
    *,
    at: str | None = None,
) -> dict[str, Any]:
    return _settle_transition_no_effect(root, path_value, at=at)


def load_request_json(value: str) -> dict[str, Any]:
    candidate = Path(value)
    payload = candidate.read_text(encoding="utf-8") if candidate.is_file() else value
    try:
        request = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Transition request must be JSON text or a JSON file") from exc
    if not isinstance(request, dict):
        raise ValueError("Transition request must be a JSON object")
    return request
