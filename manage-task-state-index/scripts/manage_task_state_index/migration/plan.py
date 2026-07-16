"""Read-only migration inspection, planning, and plan validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .classification import (
    _bind_quarantine_corrections,
    _classify_rows,
    _make_corrections,
    _manifest_payload,
    _strict_reader_probe,
    _versioned,
    _validate_quarantine_correction_bindings,
)
from .contracts import (
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MIGRATION_EVENT_FIELD,
    PLAN_SCHEMA_VERSION,
    SEAL_KIND,
    TOOL_VERSION,
    MigrationError,
)
from .mapping import _physical_lines, _token, _validate_mapping
from .storage import (
    _canonical_bytes,
    _event_bytes,
    _index_path,
    _read_json,
    _root_identity,
    _sha256,
    _validate_plan_anchors,
)

def inspect_store(root: Path) -> dict[str, Any]:
    root = root.resolve()
    prefix = _index_path(root).read_bytes()
    token_sets: dict[str, set[str]] = {"events": set(), "statuses": set(), "types": set()}
    malformed: list[dict[str, Any]] = []
    future: list[dict[str, Any]] = []
    strict_invalid: list[dict[str, Any]] = []
    for line_no, raw in enumerate(_physical_lines(prefix), start=1):
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed.append({"line": line_no, "raw_line_sha256": _sha256(raw), "reason": "malformed_json_or_utf8"})
            strict_invalid.append({"line": line_no, "raw_line_sha256": _sha256(raw), "reason": "malformed_json_or_utf8", "deterministic_identity": None})
            continue
        if not isinstance(value, dict):
            malformed.append({"line": line_no, "raw_line_sha256": _sha256(raw), "reason": "non_object_row"})
            strict_invalid.append({"line": line_no, "raw_line_sha256": _sha256(raw), "reason": "non_object_row", "deterministic_identity": None})
            continue
        token_sets["events"].add(_token(value.get("event")))
        token_sets["statuses"].add(_token(value.get("status")))
        token_sets["types"].add(_token(value.get("type")))
        if (isinstance(value.get("format_version"), int) and value["format_version"] > INDEX_FORMAT_VERSION) or (
            isinstance(value.get("schema_version"), int) and value["schema_version"] > INDEX_SCHEMA_VERSION
        ):
            future.append({"line": line_no, "raw_line_sha256": _sha256(raw)})
        strict_reason = _strict_reader_probe(value)
        if strict_reason is not None:
            strict_invalid.append({
                "line": line_no, "raw_line_sha256": _sha256(raw), "reason": strict_reason,
                "deterministic_identity": value.get("id") if isinstance(value.get("id"), str) else None,
            })
    return {
        "root_identity": _root_identity(root),
        "index_path": ".task/index.jsonl",
        "index_sha256": _sha256(prefix),
        "index_byte_length": len(prefix),
        "raw_row_count": len(_physical_lines(prefix)),
        "exact_tokens": {key: sorted(values) for key, values in token_sets.items()},
        "malformed_rows": malformed,
        "future_rows": future,
        "strict_reader_invalid_rows": strict_invalid,
        "strict_reader_invalid_count": len(strict_invalid),
        "mutation_performed": False,
    }


def build_plan(
    root: Path,
    expected_index_sha256: str,
    current_task_id: str,
    current_task_path: str,
    current_task_sha256: str,
    current_pack_id: str,
    current_pack_path: str,
    current_pack_sha256: str,
    mapping_path: Path,
) -> dict[str, Any]:
    root = root.resolve()
    prefix_path = _index_path(root)
    prefix = prefix_path.read_bytes()
    if _sha256(prefix) != expected_index_sha256:
        raise MigrationError("Source index SHA-256 drifted before planning")
    anchor_contract = {
        "anchors": {
            "current_task": {"id": current_task_id, "path": current_task_path, "sha256": current_task_sha256},
            "current_pack": {"id": current_pack_id, "path": current_pack_path, "sha256": current_pack_sha256},
        }
    }
    _validate_plan_anchors(root, anchor_contract)

    mapping_path = mapping_path.resolve(strict=True)
    mapping = _read_json(mapping_path, "mapping manifest")
    _validate_mapping(mapping)
    mapping_bytes = mapping_path.read_bytes()
    rows, normalized_events, counts = _classify_rows(prefix, mapping)
    seed = {
        "source_sha256": expected_index_sha256,
        "mapping_sha256": _sha256(mapping_bytes),
        "current_task_id": current_task_id,
        "current_task_sha256": current_task_sha256,
        "current_pack_id": current_pack_id,
        "current_pack_sha256": current_pack_sha256,
    }
    migration_id = f"tsm-{_sha256(_canonical_bytes(seed))[:24]}"
    corrections, projection = _make_corrections(
        normalized_events, mapping, migration_id,
        current_task_id, current_task_path, current_task_sha256,
        current_pack_id, current_pack_path, current_pack_sha256,
    )
    _bind_quarantine_corrections(rows, corrections, current_task_id, current_pack_id)
    _validate_quarantine_correction_bindings(rows, corrections)
    manifest = _manifest_payload(migration_id, prefix, rows, counts)
    manifest_sha = _sha256(_canonical_bytes(manifest))
    tx_ref = f".task/migrations/{migration_id}"
    correction_payload = _event_bytes(corrections)
    joiner = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    correction_segment = joiner + correction_payload
    core: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": "task_state_index_migration_plan",
        "tool_version": TOOL_VERSION,
        "migration_id": migration_id,
        "root_identity": _root_identity(root),
        "source_prefix": {
            "ref": ".task/index.jsonl", "sha256": expected_index_sha256,
            "byte_length": len(prefix), "raw_row_count": len(rows),
        },
        "mapping_manifest": {
            "source_ref": str(mapping_path), "sha256": _sha256(mapping_bytes),
            "schema_version": mapping["schema_version"], "mapping_policy_id": mapping["mapping_policy_id"],
            "snapshot_ref": f"{tx_ref}/mapping-manifest.json",
        },
        "resolution_manifest": {"ref": f"{tx_ref}/resolution-manifest.json", "sha256": manifest_sha},
        "source_snapshot_ref": f"{tx_ref}/legacy-prefix.jsonl",
        "plan_snapshot_ref": f"{tx_ref}/plan.json",
        "classification_counts": counts,
        "unclassified_count": counts["blocked_unknown_or_future"],
        "rows": rows,
        "correction_events": corrections,
        "projection": projection,
        "anchors": {
            "current_task": {"id": current_task_id, "path": current_task_path, "sha256": current_task_sha256},
            "current_pack": {"id": current_pack_id, "path": current_pack_path, "sha256": current_pack_sha256},
        },
        "effective_at": mapping["effective_at"],
        "transaction_directory_ref": tx_ref,
        "historical_rows_removed": 0,
        "historical_rows_reordered": 0,
        "original_row_bytes_modified": 0,
        "prefix_preserved": True,
    }
    contract_sha = _sha256(_canonical_bytes(core))
    seal_id = f"schema-{migration_id}-seal"
    seal = _versioned({
        "event": "upsert", "id": seal_id, "type": "schema_contract", "status": "informational",
        "path": f"{tx_ref}/receipt.json", "title": "Task state legacy migration seal",
        "updated_at": mapping["effective_at"],
        "fields": {
            MIGRATION_EVENT_FIELD: SEAL_KIND,
            "migration_id": migration_id,
            "plan_contract_sha256": contract_sha,
            "source_prefix_sha256": expected_index_sha256,
            "source_prefix_byte_length": len(prefix),
            "source_raw_row_count": len(rows),
            "mapping_manifest_sha256": _sha256(mapping_bytes),
            "resolution_manifest_sha256": manifest_sha,
            "correction_suffix_sha256": _sha256(correction_segment),
            "correction_suffix_byte_length": len(correction_segment),
        },
    })
    seal_line = _canonical_bytes(seal)
    boundary = prefix + correction_segment + seal_line
    plan = {
        **core,
        "plan_contract_sha256": contract_sha,
        "correction_suffix": {
            "ref": f"{tx_ref}/correction-suffix.jsonl", "sha256": _sha256(correction_segment),
            "byte_length": len(correction_segment), "event_count": len(corrections),
            "offset": len(prefix),
        },
        "seal": {
            "id": seal_id, "event": seal, "line_sha256": _sha256(seal_line),
            "offset": len(prefix) + len(correction_segment), "byte_length": len(seal_line),
        },
        "expected_after_index_sha256": _sha256(boundary),
        "expected_commit_boundary_byte_length": len(boundary),
        "receipt_ref": f"{tx_ref}/receipt.json",
        "receipt_anchor_id": seal_id,
        "journal_ref": f"{tx_ref}/journal.json",
        "prepare_journal_ref": f"{tx_ref}/journal-prepare.json",
        "completion_marker_ref": f"{tx_ref}/journal-completion.json",
        "render_snapshot_ref": f"{tx_ref}/rendered-index.md",
    }
    return plan


def _plan_manifest(plan: dict[str, Any]) -> dict[str, Any]:
    prefix_meta = plan["source_prefix"]
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": "task_state_index_resolution_manifest",
        "migration_id": plan["migration_id"],
        "source_prefix_sha256": prefix_meta["sha256"],
        "source_prefix_byte_length": prefix_meta["byte_length"],
        "source_raw_row_count": prefix_meta["raw_row_count"],
        "classification_counts": plan["classification_counts"],
        "rows": plan["rows"],
        "raw_row_bodies_included": False,
    }


def _validate_plan_contract(root: Path, plan_path: Path, expected_plan_sha: str, expected_index_sha: str) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    plan_bytes = plan_path.read_bytes()
    if _sha256(plan_bytes) != expected_plan_sha:
        raise MigrationError("Plan SHA-256 mismatch")
    plan = _read_json(plan_path, "migration plan")
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION or plan.get("kind") != "task_state_index_migration_plan":
        raise MigrationError("Unsupported migration plan")
    if plan.get("source_prefix", {}).get("sha256") != expected_index_sha:
        raise MigrationError("Expected source SHA does not match plan")
    if plan.get("root_identity") != _root_identity(root):
        raise MigrationError("Plan root identity mismatch")
    core_keys = {
        "schema_version", "kind", "tool_version", "migration_id", "root_identity", "source_prefix",
        "mapping_manifest", "resolution_manifest", "source_snapshot_ref", "plan_snapshot_ref",
        "classification_counts", "unclassified_count", "rows", "correction_events", "projection",
        "anchors", "effective_at", "transaction_directory_ref", "historical_rows_removed",
        "historical_rows_reordered", "original_row_bytes_modified", "prefix_preserved",
    }
    core = {key: plan[key] for key in core_keys}
    if _sha256(_canonical_bytes(core)) != plan.get("plan_contract_sha256"):
        raise MigrationError("Plan contract digest mismatch")
    mapping_source = Path(plan["mapping_manifest"]["source_ref"])
    mapping_bytes = mapping_source.read_bytes()
    if _sha256(mapping_bytes) != plan["mapping_manifest"]["sha256"]:
        raise MigrationError("Mapping manifest drifted after planning")
    mapping = _read_json(mapping_source, "mapping manifest")
    _validate_mapping(mapping)
    manifest = _plan_manifest(plan)
    if _sha256(_canonical_bytes(manifest)) != plan["resolution_manifest"]["sha256"]:
        raise MigrationError("Resolution manifest digest mismatch")
    # The exact segment (including a possible delimiter) is reconstructed from
    # the planned offset/length and the source bytes below.
    current_index = _index_path(root).read_bytes()
    prefix_length = plan["source_prefix"]["byte_length"]
    if len(current_index) < prefix_length:
        raise MigrationError("Source prefix drifted after planning")
    prefix = current_index[:prefix_length]
    if _sha256(prefix) != plan["source_prefix"]["sha256"]:
        raise MigrationError("Source prefix drifted after planning")
    joiner = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    correction_segment = joiner + _event_bytes(plan["correction_events"])
    if _sha256(correction_segment) != plan["correction_suffix"]["sha256"] or len(correction_segment) != plan["correction_suffix"]["byte_length"]:
        raise MigrationError("Correction suffix digest mismatch")
    seal_line = _canonical_bytes(plan["seal"]["event"])
    if _sha256(seal_line) != plan["seal"]["line_sha256"]:
        raise MigrationError("Seal digest mismatch")
    if _sha256(prefix + correction_segment + seal_line) != plan["expected_after_index_sha256"]:
        raise MigrationError("Expected commit boundary digest mismatch")
    return plan, plan_bytes, mapping, mapping_bytes
