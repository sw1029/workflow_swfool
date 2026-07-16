"""Verify the committed boundary, anchor, and live ledger projection."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .core import (
    VerificationError,
    _canonical_json,
    _merge_event_into_state,
    _merge_state,
    _regular_file,
    _require,
    _sha256,
    _validate_suffix_event,
)
from .correction_evidence import _anchor_event
from .projection_evidence import _current_projection

def _parse_current_ledger(
    bundle: dict[str, Any], rebuilt: dict[str, Any], publication: dict[str, Any]
) -> dict[str, Any]:
    root, plan = bundle["root"], rebuilt["plan"]
    ledger_path = _regular_file(root / ".task" / "index.jsonl", "current task-state index")
    boundary_length = plan["expected_commit_boundary_byte_length"]
    anchor = _anchor_event(plan, publication["receipt_sha"], publication["journal_sha"], publication["marker_sha"])
    anchor_line = _canonical_json(anchor)
    _require(boundary_length == bundle["receipt"]["commit_boundary_length"], "receipt anchor offset differs from commit boundary length")
    known_ids = {event["id"] for event in rebuilt["normalized"] if isinstance(event.get("id"), str) and event["id"]}
    sealed_events = rebuilt["corrections"] + [plan["seal"]["event"], anchor]
    state = _merge_state(rebuilt["normalized"])
    for event in sealed_events:
        _validate_suffix_event(event, known_ids)
        _merge_event_into_state(state, event)
    event_count = len(rebuilt["normalized"]) + len(sealed_events)
    post_anchor_lines = 0
    digest = hashlib.sha256()
    with ledger_path.open("rb") as handle:
        for part in rebuilt["boundary_parts"]:
            view = memoryview(part)
            offset = 0
            while offset < len(part):
                chunk = handle.read(min(1024 * 1024, len(part) - offset))
                _require(chunk == view[offset:offset + len(chunk)] and chunk, "current ledger historical commit boundary mismatch")
                digest.update(chunk)
                offset += len(chunk)
        observed_anchor = handle.read(len(anchor_line))
        _require(observed_anchor == anchor_line, "receipt anchor is not located exactly at the commit boundary")
        digest.update(observed_anchor)
        for raw in handle:
            digest.update(raw)
            post_anchor_lines += 1
            if not raw.strip():
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise VerificationError(f"post-anchor ledger row is malformed: {exc}") from exc
            _require(isinstance(event, dict), "post-anchor ledger row is not an object")
            _validate_suffix_event(event, known_ids)
            _merge_event_into_state(state, event)
            event_count += 1
    current_projection, current_identities = _current_projection(state, root)
    historical_basis = {
        "transaction_id": plan["migration_id"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "canonical_task": plan["anchors"]["current_task"],
        "canonical_pack": plan["anchors"]["current_pack"],
        "projection": rebuilt["projection"],
    }
    current_basis = {
        "task": current_identities["task"],
        "pack": current_identities["pack"],
        "projection": current_projection,
    }
    return {
        "ledger_sha256": digest.hexdigest(),
        "historical_boundary_task_id": plan["anchors"]["current_task"]["id"],
        "historical_boundary_pack_id": plan["anchors"]["current_pack"]["id"],
        "historical_boundary_evidence_ref": f"{bundle['receipt']['plan_ref']}#anchors",
        "historical_boundary_identity_sha256": _sha256(_canonical_json(historical_basis)),
        "post_migration_current_task_id": current_identities["task"]["id"],
        "post_migration_current_pack_id": current_identities["pack"]["id"],
        "post_migration_current_evidence_ref": ".task/index.jsonl#post_anchor_projection",
        "post_migration_current_identity_sha256": _sha256(_canonical_json(current_basis)),
        "post_anchor_event_count": post_anchor_lines,
        "current_event_count": event_count,
        "anchor_sha256": _sha256(anchor_line),
    }
