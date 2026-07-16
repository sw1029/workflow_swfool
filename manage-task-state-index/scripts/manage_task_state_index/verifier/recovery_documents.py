"""Independent recovery-plan, journal, and anchor reconstruction."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .core import (
    ANCHOR_KIND,
    MIGRATION_EVENT_FIELD,
    _canonical_json,
    _load_json,
    _physical_lines,
    _require,
    _sha256,
    _transaction_ref,
    _workspace_ref,
)
from .recovery_contracts import ZERO_SHA256

def _load_plan(root: Path, transaction_id: str) -> tuple[dict[str, Any], bytes]:
    _require(re.fullmatch(r"tsm-[0-9a-f]{24}", transaction_id) is not None, "transaction identity is invalid")
    path = _transaction_ref(root, f".task/migrations/{transaction_id}/plan.json", transaction_id, "plan")
    plan, payload = _load_json(path, "plan")
    _require(payload == _canonical_json(plan) and plan.get("migration_id") == transaction_id, "recovery plan identity or encoding is invalid")
    for field in (
        "source_snapshot_ref", "plan_snapshot_ref", "journal_ref", "receipt_ref",
        "completion_marker_ref", "render_snapshot_ref", "prepare_journal_ref",
    ):
        _require(isinstance(plan.get(field), str) and plan[field], f"recovery plan lacks {field}")
    for field, nested in (("mapping_manifest", "snapshot_ref"), ("resolution_manifest", "ref"), ("correction_suffix", "ref")):
        _require(isinstance(plan.get(field), dict) and isinstance(plan[field].get(nested), str), f"recovery plan lacks {field}.{nested}")
    return plan, payload

def _planned_boundary(root: Path, plan: dict[str, Any]) -> bytes:
    prefix = _workspace_ref(root, plan["source_snapshot_ref"], "recovery source snapshot").read_bytes()
    correction = _workspace_ref(root, plan["correction_suffix"]["ref"], "recovery correction suffix").read_bytes()
    seal = _canonical_json(plan["seal"]["event"])
    boundary = prefix + correction + seal
    _require(
        len(boundary) == plan["expected_commit_boundary_byte_length"]
        and _sha256(boundary) == plan["expected_after_index_sha256"],
        "recovery plan boundary is not independently reproducible",
    )
    return boundary

def _journal_base(
    plan: dict[str, Any], plan_sha: str, *, committed: bool = False
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": (
            "task_state_index_migration_journal"
            if committed else "task_state_index_migration_journal_prepare"
        ),
        "transaction_id": plan["migration_id"],
        "prefix_sha256": plan["source_prefix"]["sha256"],
        "prefix_byte_length": plan["source_prefix"]["byte_length"],
        "expected_boundary_sha256": plan["expected_after_index_sha256"],
        "expected_boundary_byte_length": plan["expected_commit_boundary_byte_length"],
        "plan_ref": plan["plan_snapshot_ref"],
        "plan_sha256": plan_sha,
    }

def _journal_base_sha(
    plan: dict[str, Any], plan_sha: str, *, committed: bool = False
) -> str:
    return _sha256(_canonical_json(_journal_base(plan, plan_sha, committed=committed)))

def _pending_journal(
    plan: dict[str, Any], plan_sha: str, state: str, updated_at: str,
    append_length: int, append_sha: str, receipt_sha: str,
) -> dict[str, Any]:
    value = {
        **_journal_base(plan, plan_sha),
        "state": state,
        "journal_updated_at": updated_at,
    }
    if state == "partial_suffix":
        value.update(appended_byte_length=append_length, appended_sha256=append_sha)
    if state in {"receipt_written", "receipt_anchored", "committed_render_pending"}:
        value["receipt_sha256"] = receipt_sha
    return value

def _anchor_observation(index: bytes, boundary_length: int, transaction_id: str) -> tuple[bool, str]:
    if len(index) <= boundary_length:
        return False, ZERO_SHA256
    lines = _physical_lines(index[boundary_length:])
    if not lines:
        return False, ZERO_SHA256
    raw = lines[0]
    try:
        event = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, ZERO_SHA256
    fields = event.get("fields") if isinstance(event, dict) and isinstance(event.get("fields"), dict) else {}
    present = fields.get(MIGRATION_EVENT_FIELD) == ANCHOR_KIND and fields.get("migration_id") == transaction_id
    return present, _sha256(raw) if present else ZERO_SHA256
