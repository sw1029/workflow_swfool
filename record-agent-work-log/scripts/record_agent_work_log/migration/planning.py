"""Plan persistence and deterministic record reconstruction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..integrity import expected_record_id, sha256_bytes, workspace_root
from .classification import _canonical_record
from .contracts import MANIFEST_SCHEMA_VERSION, PLAN_SCHEMA_VERSION, MigrationError
from .inventory import _inventory_document, _split_source_rows
from .plan_builder import _build_plan
from .storage import _canonical_json_bytes, _read_index, _resolve_ref, _strict_atomic_replace


def write_plan(
    root_raw: str | Path,
    *,
    expected_index_sha256: str,
    status_map_raw: str | Path,
    output_raw: str | Path,
) -> dict[str, Any]:
    root = workspace_root(root_raw)
    source_payload = _read_index(root)
    actual_sha = sha256_bytes(source_payload)
    if actual_sha != expected_index_sha256:
        raise MigrationError(f"source index drift: expected {expected_index_sha256}, observed {actual_sha}")
    status_map_path = _resolve_ref(root, str(status_map_raw))
    plan, _ = _build_plan(root, status_map_path)
    output = Path(output_raw).expanduser().absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or (output.exists() and not output.is_file()):
        raise MigrationError("plan output must be a regular non-symlink file")
    payload = _canonical_json_bytes(plan)
    _strict_atomic_replace(output, payload)
    return {
        "status": "planned" if plan["unresolved_count"] == 0 else "blocked",
        "plan": str(output),
        "plan_sha256": sha256_bytes(payload),
        "migration_id": plan["migration_id"],
        "unresolved_count": plan["unresolved_count"],
        "expected_after_index_sha256": plan["expected_after_index_sha256"],
    }

def _load_plan(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    try:
        plan = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"plan is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise MigrationError(f"plan schema_version must be {PLAN_SCHEMA_VERSION}")
    return plan, payload

def _canonical_records_from_plan(root: Path, plan: dict[str, Any]) -> tuple[list[dict[str, Any]], bytes]:
    source_payload = _read_index(root)
    source_rows = {row["source_line"]: row for row in _split_source_rows(source_payload)}
    inventory = _inventory_document(root, source_payload)
    markdown_by_path = {item["path"]: item for item in inventory["markdown"]}
    records: list[dict[str, Any]] = []
    plan_rows = plan.get("rows")
    if not isinstance(plan_rows, list):
        raise MigrationError("plan rows are missing")
    for row_entry in plan_rows:
        if row_entry.get("classification") != "canonical_log":
            continue
        source_line = row_entry.get("source_line")
        source = source_rows.get(source_line)
        if source is None or source["source_row_sha256"] != row_entry.get("source_row_sha256"):
            raise MigrationError(f"source row drift at line {source_line}")
        path = row_entry.get("source_path")
        if not isinstance(path, str) or path not in markdown_by_path:
            raise MigrationError(f"planned canonical body is unavailable: {path}")
        records.append(
            _canonical_record(
                root=root,
                migration_id=plan["migration_id"],
                source=source,
                path=path,
                body_sha=markdown_by_path[path]["body_sha256"],
                normalized_status=row_entry["normalized_status"],
                mapping_reason=row_entry["status_mapping_reason"],
                original_status=row_entry["original_status"],
                orphan=False,
            )
        )
    for orphan in plan.get("orphans", []):
        if orphan.get("disposition") != "bind_as_legacy_import":
            continue
        path = orphan.get("path")
        if not isinstance(path, str) or path not in markdown_by_path:
            raise MigrationError(f"planned orphan body is unavailable: {path}")
        if markdown_by_path[path]["body_sha256"] != orphan.get("body_sha256"):
            raise MigrationError(f"planned orphan body drift: {path}")
        records.append(
            _canonical_record(
                root=root,
                migration_id=plan["migration_id"],
                source=None,
                path=path,
                body_sha=orphan["body_sha256"],
                normalized_status="informational",
                mapping_reason="orphan_body_structure_not_evaluated",
                original_status=None,
                orphan=True,
            )
        )
    # Apply the same deterministic duplicate-log-id aliasing as planning.
    seen: set[str] = set()
    for record in records:
        if record["log_id"] in seen:
            record["original_log_id"] = record["log_id"]
            record["log_id"] = "log-legacy-" + sha256_bytes(
                (record["path"] + "\0" + record["body_sha256"]).encode("utf-8")
            )[:32]
            record["record_id"] = expected_record_id(record)
        seen.add(record["log_id"])
    payload = b"".join(_canonical_json_bytes(record) for record in records)
    return records, payload

def _manifest_for(plan: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": "agent_log_migration_resolution_manifest",
        "migration_id": plan["migration_id"],
        "source_index_sha256": plan["source_index"]["sha256"],
        "source_inventory_sha256": plan["source_inventory_sha256"],
        "source_rows": plan["rows"],
        "markdown_inventory": inventory["markdown"],
        "markdown_resolutions": plan["body_resolutions"],
        "orphans": plan["orphans"],
        "classification_counts": plan["classification_counts"],
        "unresolved_count": plan["unresolved_count"],
        "body_mutation_count": 0,
        "historical_claims_upgraded": False,
    }
