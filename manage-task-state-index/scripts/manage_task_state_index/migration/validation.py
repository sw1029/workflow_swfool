"""Sealed-reader validation and migration boundary projections."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .classification import (
    _merge_state,
    _validate_quarantine_correction_bindings,
    _versioned,
)
from .contracts import (
    CLASSIFICATIONS,
    MIGRATION_EVENT_FIELD,
    SEAL_KIND,
    MigrationError,
)
from .mapping import (
    _physical_lines,
    _validate_current_event,
    validate_current_suffix_event,
)
from .storage import (
    _atomic_write,
    _canonical_bytes,
    _index_path,
    _read_json,
    _safe_ref,
    _sha256,
    _sha_file,
)
from .graph import _find_anchor_lines, _matching_plan_anchor, _validate_journal_base
from .publication import _committed_journal_payload, _completion_marker_payload
from .projection import _current_projection, _migration_boundary_projection
from .projection import (
    _normalized_events_from_plan,
)

def _forward_complete_anchored(
    root: Path, plan: dict[str, Any], payload: bytes,
) -> dict[str, Any]:
    matching = _matching_plan_anchor(payload, plan)
    if matching is None:
        raise MigrationError("Forward completion requires the exact transaction anchor")
    events, _results, receipt = _validate_receipt_graph(
        root, payload, *matching, allow_pending_completion=True,
    )
    marker_path = _safe_ref(root, receipt["completion_marker_ref"], must_exist=False)
    if marker_path.exists():
        raise MigrationError("Completion marker exists but the committed graph is invalid")
    prepare_path = _safe_ref(root, receipt["prepare_journal_ref"])
    prepare = _read_json(prepare_path, "immutable migration prepare journal")
    committed_at = receipt.get("transaction_committed_at")
    recovery_status = receipt.get("recovery_status")
    if not isinstance(committed_at, str) or not isinstance(recovery_status, str):
        raise MigrationError("Migration receipt lacks completion timing or recovery status")
    expected_journal = _canonical_bytes(_committed_journal_payload(
        plan, prepare, committed_at, receipt["rendered_index_sha256"], recovery_status,
    ))
    expected_marker = _canonical_bytes(_completion_marker_payload(
        plan, receipt["prepare_journal_sha256"], _sha256(expected_journal),
        receipt["rendered_index_sha256"], recovery_status, committed_at,
        receipt["plan_sha256"],
    ))
    if _sha256(expected_journal) != receipt["journal_sha256"]:
        raise MigrationError("Receipt does not bind the reconstructable committed journal")
    if _sha256(expected_marker) != receipt["completion_marker_sha256"]:
        raise MigrationError("Receipt does not bind the reconstructable completion marker")
    journal_path = _safe_ref(root, receipt["journal_ref"])
    if journal_path.read_bytes() != expected_journal:
        pending = _read_json(journal_path, "pending migration journal")
        _validate_journal_base(pending, prepare)
        if pending.get("state") not in {"receipt_written", "receipt_anchored", "committed_render_pending"}:
            raise MigrationError("Pending journal state is not eligible for forward completion")
        receipt_sha = _sha_file(_safe_ref(root, plan["receipt_ref"]))
        if pending.get("receipt_sha256") != receipt_sha:
            raise MigrationError("Pending journal does not bind the anchored receipt")
    render = _safe_ref(root, receipt["rendered_index_ref"]).read_bytes()
    _atomic_write(journal_path, expected_journal)
    _atomic_write(marker_path, expected_marker)
    _atomic_write(root / ".task" / "index.md", render)
    checked_events, _checked_results, _checked_receipt = _validate_receipt_graph(
        root, _index_path(root).read_bytes(), *matching,
    )
    return {
        "idempotent": True,
        "transaction_id": plan["migration_id"],
        "receipt_ref": plan["receipt_ref"],
        "receipt_sha256": _sha_file(_safe_ref(root, plan["receipt_ref"])),
        "event_count": len(checked_events),
        "recovery_status": "forward_completed",
    }

def _load_receipt_binding(
    root: Path,
    payload: bytes,
    anchor: dict[str, Any],
) -> tuple[str, dict[str, Any], int, bytes]:
    _validate_current_event(anchor)
    fields = anchor.get("fields", {})
    receipt_ref = fields.get("receipt_ref")
    receipt_sha = fields.get("receipt_sha256")
    if not isinstance(receipt_ref, str) or not isinstance(receipt_sha, str):
        raise MigrationError("Migration receipt anchor lacks exact receipt binding")
    receipt_path = _safe_ref(root, receipt_ref)
    receipt_bytes = receipt_path.read_bytes()
    if _sha256(receipt_bytes) != receipt_sha:
        raise MigrationError("Migration receipt digest mismatch")
    receipt = _read_json(receipt_path, "migration receipt")
    if receipt.get("kind") != "task_state_index_migration" or receipt.get("status") != "committed":
        raise MigrationError("Migration receipt is not committed")
    if (
        receipt.get("transaction_id") != fields.get("migration_id")
        or receipt.get("seal_sha256") != fields.get("seal_sha256")
    ):
        raise MigrationError("Migration receipt subject mismatch")
    for key in ("journal_ref", "journal_sha256", "completion_marker_ref", "completion_marker_sha256"):
        if fields.get(key) != receipt.get(key):
            raise MigrationError("Migration anchor completion binding mismatch")
    prefix_len = receipt.get("source_prefix_byte_length")
    if not isinstance(prefix_len, int) or prefix_len < 0 or len(payload) < prefix_len:
        raise MigrationError("Invalid sealed prefix boundary")
    prefix = payload[:prefix_len]
    if _sha256(prefix) != receipt.get("source_prefix_sha256"):
        raise MigrationError("Sealed prefix digest mismatch")
    if _safe_ref(root, receipt["source_prefix_ref"]).read_bytes() != prefix:
        raise MigrationError("Immutable prefix snapshot is not byte-identical")
    return receipt_ref, receipt, prefix_len, prefix


def _validate_receipt_sidecars(
    root: Path,
    receipt_ref: str,
    receipt: dict[str, Any],
    *,
    allow_pending_completion: bool,
) -> None:
    for ref_key, sha_key in (
        ("mapping_manifest_ref", "mapping_manifest_sha256"),
        ("resolution_manifest_ref", "resolution_manifest_sha256"),
        ("plan_ref", "plan_sha256"),
        ("correction_suffix_ref", "correction_suffix_sha256"),
        ("rendered_index_ref", "rendered_index_sha256"),
        ("prepare_journal_ref", "prepare_journal_sha256"),
    ):
        if _sha_file(_safe_ref(root, receipt[ref_key])) != receipt[sha_key]:
            raise MigrationError(f"Migration sidecar digest mismatch: {ref_key}")
    if allow_pending_completion:
        return
    for ref_key, sha_key in (
        ("journal_ref", "journal_sha256"),
        ("completion_marker_ref", "completion_marker_sha256"),
    ):
        if _sha_file(_safe_ref(root, receipt[ref_key])) != receipt[sha_key]:
            raise MigrationError(f"Migration sidecar digest mismatch: {ref_key}")
    journal = _read_json(_safe_ref(root, receipt["journal_ref"]), "committed migration journal")
    marker = _read_json(
        _safe_ref(root, receipt["completion_marker_ref"]),
        "migration completion marker",
    )
    if journal.get("state") != "committed" or journal.get("transaction_id") != receipt["transaction_id"]:
        raise MigrationError("Committed migration journal subject mismatch")
    marker_bindings = {
        "kind": "task_state_index_migration_completion_marker",
        "transaction_id": receipt["transaction_id"],
        "state": "committed",
        "prepare_journal_ref": receipt["prepare_journal_ref"],
        "prepare_journal_sha256": receipt["prepare_journal_sha256"],
        "journal_ref": receipt["journal_ref"],
        "journal_sha256": receipt["journal_sha256"],
        "receipt_ref": receipt_ref,
        "plan_ref": receipt["plan_ref"],
        "plan_sha256": receipt["plan_sha256"],
        "seal_sha256": receipt["seal_sha256"],
        "commit_boundary_length": receipt["commit_boundary_length"],
        "commit_boundary_sha256": receipt["commit_boundary_sha256"],
        "rendered_index_ref": receipt["rendered_index_ref"],
        "rendered_index_sha256": receipt["rendered_index_sha256"],
        "recovery_status": receipt["recovery_status"],
    }
    if any(marker.get(key) != value for key, value in marker_bindings.items()):
        raise MigrationError("Migration completion marker graph mismatch")


def _validate_resolution_manifest(
    root: Path,
    receipt: dict[str, Any],
    prefix: bytes,
) -> tuple[list[dict[str, Any]], list[bytes]]:
    manifest = _read_json(
        _safe_ref(root, receipt["resolution_manifest_ref"]),
        "resolution manifest",
    )
    if (
        manifest.get("migration_id") != receipt["transaction_id"]
        or manifest.get("source_prefix_sha256") != receipt["source_prefix_sha256"]
    ):
        raise MigrationError("Resolution manifest subject mismatch")
    raw_lines = _physical_lines(prefix)
    rows = manifest.get("rows")
    if (
        not isinstance(rows, list)
        or len(rows) != len(raw_lines)
        or len(raw_lines) != receipt["source_raw_row_count"]
    ):
        raise MigrationError("Resolution manifest does not account for every prefix row")
    seen: set[tuple[int, str]] = set()
    for line_no, (raw, entry) in enumerate(zip(raw_lines, rows, strict=True), start=1):
        if (
            not isinstance(entry, dict)
            or entry.get("line") != line_no
            or entry.get("raw_line_sha256") != _sha256(raw)
        ):
            raise MigrationError("Resolution manifest line/hash mismatch")
        key = (line_no, entry["raw_line_sha256"])
        if key in seen or entry.get("classification") not in CLASSIFICATIONS:
            raise MigrationError("Resolution manifest has duplicate or invalid disposition")
        seen.add(key)
    if any(entry.get("classification") == "blocked_unknown_or_future" for entry in rows):
        raise MigrationError("Committed manifest contains blocked rows")
    return rows, raw_lines


def _validate_commit_boundary(
    payload: bytes,
    receipt: dict[str, Any],
    prefix_len: int,
    anchor_offset: int,
) -> bytes:
    correction_offset = receipt["correction_suffix_offset"]
    correction_length = receipt["correction_suffix_byte_length"]
    seal_offset = receipt["seal_offset"]
    seal_length = receipt["seal_byte_length"]
    if correction_offset != prefix_len or seal_offset != correction_offset + correction_length:
        raise MigrationError("Migration boundary offsets are inconsistent")
    correction = payload[correction_offset:seal_offset]
    if len(correction) != correction_length or _sha256(correction) != receipt["correction_suffix_sha256"]:
        raise MigrationError("Correction suffix boundary mismatch")
    seal_raw = payload[seal_offset:seal_offset + seal_length]
    if len(seal_raw) != seal_length or _sha256(seal_raw) != receipt["seal_sha256"]:
        raise MigrationError("Migration seal boundary mismatch")
    boundary_len = receipt["commit_boundary_length"]
    if boundary_len != seal_offset + seal_length or _sha256(payload[:boundary_len]) != receipt["commit_boundary_sha256"]:
        raise MigrationError("Migration commit boundary mismatch")
    try:
        seal = json.loads(seal_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError("Migration seal is invalid JSON") from exc
    _validate_current_event(seal)
    seal_fields = seal.get("fields", {})
    if (
        seal_fields.get(MIGRATION_EVENT_FIELD) != SEAL_KIND
        or seal_fields.get("migration_id") != receipt["transaction_id"]
    ):
        raise MigrationError("Migration seal subject mismatch")
    if (
        seal_fields.get("plan_contract_sha256") != receipt["plan_contract_sha256"]
        or seal_fields.get("resolution_manifest_sha256") != receipt["resolution_manifest_sha256"]
    ):
        raise MigrationError("Migration seal graph binding mismatch")
    if anchor_offset < boundary_len:
        raise MigrationError("Receipt anchor precedes migration seal")
    return correction


def _load_projection_events(
    root: Path,
    payload: bytes,
    receipt: dict[str, Any],
    prefix_len: int,
    correction: bytes,
    manifest_rows: list[dict[str, Any]],
    raw_lines: list[bytes],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plan = _read_json(_safe_ref(root, receipt["plan_ref"]), "sealed migration plan")
    if plan.get("rows") != manifest_rows:
        raise MigrationError("Plan and resolution manifest row bindings differ")
    correction_events: list[dict[str, Any]] = []
    for raw in _physical_lines(correction):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MigrationError("Correction suffix contains malformed JSON") from exc
        if not isinstance(event, dict):
            raise MigrationError("Correction suffix contains a non-object event")
        _validate_current_event(event)
        correction_events.append(event)
    _validate_quarantine_correction_bindings(manifest_rows, correction_events)
    events = _normalized_events_from_plan(root, plan)
    known_ids = {
        str(event["id"])
        for event in events
        if isinstance(event.get("id"), str) and event["id"]
    }
    suffix_events: list[dict[str, Any]] = []
    suffix_results: list[dict[str, Any]] = []
    for relative_line_no, raw in enumerate(_physical_lines(payload[prefix_len:]), start=1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MigrationError("Malformed post-prefix suffix row") from exc
        if not isinstance(event, dict):
            raise MigrationError("Non-object post-prefix suffix row")
        validate_current_suffix_event(event, known_ids)
        suffix_events.append(event)
        suffix_results.append({
            "line_no": len(raw_lines) + relative_line_no,
            "migration_status": "current",
            "projection_impact": "independent",
            "row_identity": event.get("id"),
            "malformed_reason": None,
        })
    prefix_results = [
        {
            "line_no": entry["line"],
            "migration_status": entry["classification"],
            "projection_impact": entry["projection_impact"],
            "row_identity": entry.get("deterministic_identity"),
            "malformed_reason": None,
        }
        for entry in manifest_rows
    ]
    return events + suffix_events, prefix_results + suffix_results


def _validate_receipt_graph(
    root: Path,
    payload: bytes,
    anchor_offset: int,
    anchor_raw: bytes,
    anchor: dict[str, Any],
    *,
    allow_pending_completion: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    del anchor_raw
    receipt_ref, receipt, prefix_len, prefix = _load_receipt_binding(
        root, payload, anchor
    )
    _validate_receipt_sidecars(
        root,
        receipt_ref,
        receipt,
        allow_pending_completion=allow_pending_completion,
    )
    manifest_rows, raw_lines = _validate_resolution_manifest(root, receipt, prefix)
    correction = _validate_commit_boundary(payload, receipt, prefix_len, anchor_offset)
    events, results = _load_projection_events(
        root,
        payload,
        receipt,
        prefix_len,
        correction,
        manifest_rows,
        raw_lines,
    )
    return events, results, receipt

def load_sealed_events_if_present(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Return exact sealed projection, or ``None`` when no seal is present.

    If any receipt-anchor marker exists but its graph is invalid, raise instead
    of falling back to permissive legacy parsing.
    """
    root = Path(root).resolve()
    index = root / ".task" / "index.jsonl"
    if not index.is_file() or index.is_symlink():
        return None
    payload = index.read_bytes()
    anchors = _find_anchor_lines(payload)
    if not anchors:
        return None
    errors: list[str] = []
    for offset, raw, anchor in reversed(anchors):
        try:
            events, results, _receipt = _validate_receipt_graph(root, payload, offset, raw, anchor)
            return events, results
        except (KeyError, TypeError, MigrationError) as exc:
            errors.append(str(exc))
    raise MigrationError("No valid task-state migration receipt graph: " + "; ".join(errors[:3]))
def validate_migration(root: Path, receipt_path: Path, flags: argparse.Namespace | None = None) -> dict[str, Any]:
    root = root.resolve()
    receipt_path = receipt_path.resolve(strict=True)
    payload = _index_path(root).read_bytes()
    anchors = _find_anchor_lines(payload)
    if not anchors:
        raise MigrationError("No committed sealed migration is present")
    receipt_sha = _sha_file(receipt_path)
    matching = [
        anchor for anchor in anchors
        if anchor[2].get("fields", {}).get("receipt_sha256") == receipt_sha
    ]
    if not matching:
        raise MigrationError("Requested receipt is not anchored")
    graph_errors: list[str] = []
    loaded_graph: tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]] | None = None
    for anchor in reversed(matching):
        try:
            loaded_graph = _validate_receipt_graph(root, payload, *anchor)
            break
        except (KeyError, TypeError, MigrationError) as exc:
            graph_errors.append(str(exc))
    if loaded_graph is None:
        raise MigrationError("Requested receipt graph is invalid: " + "; ".join(graph_errors[:3]))
    events, _results, receipt = loaded_graph
    boundary = _migration_boundary_projection(root, receipt)
    state = _merge_state(events)
    current = _current_projection(state)
    appendable = False
    if current["current_active_task_id"] is not None:
        append_probe = _versioned({
            "event": "link", "id": current["current_active_task_id"],
            "updated_at": receipt["transaction_committed_at"], "links": [],
        })
        validate_current_suffix_event(append_probe, set(state))
        appendable = True
    prefix_preserved = (
        _safe_ref(root, receipt["source_prefix_ref"]).read_bytes()
        == payload[:receipt["source_prefix_byte_length"]]
    )
    checks = {
        "strict_reader_status": "pass",
        "append_simulation_status": "pass" if appendable else "fail",
        **current,
        **boundary,
        "prefix_preserved": prefix_preserved,
    }
    if flags is not None:
        requirements = {
            "require_current_projection_evaluated": checks["current_projection_status"] == "evaluated",
            "require_single_active_task": checks["active_task_count"] == 1,
            "require_single_active_pack": checks["active_pack_count"] == 1,
            "require_appendable": checks["append_simulation_status"] == "pass",
        }
        failed = [name for name, passed in requirements.items() if getattr(flags, name, False) and not passed]
        if failed:
            raise MigrationError("Migration validation requirement failed: " + ", ".join(failed))
    if (
        checks["projection_completeness"] != "complete"
        or checks["append_simulation_status"] != "pass"
        or not checks["prefix_preserved"]
    ):
        raise MigrationError("Committed migration projection or prefix integrity is incomplete")
    return {"valid": True, "receipt": receipt, **checks}
