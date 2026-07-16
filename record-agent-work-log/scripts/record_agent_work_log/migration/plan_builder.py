"""Deterministic migration plan orchestration."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ..integrity import sha256_bytes
from .classification import _load_status_map
from .contracts import TOOL_VERSION
from .inventory import _inventory_document, _split_source_rows
from .plan_bodies import build_body_resolutions, deduplicate_body_aliases
from .plan_output import (
    build_canonical_records,
    build_plan_document,
    finalize_record_identifiers,
)
from .plan_rows import classify_source_rows, select_canonical_sources
from .storage import _canonical_json_bytes, _read_index, _root_identity


def _build_plan(root: Path, status_map_path: Path) -> tuple[dict[str, Any], bytes]:
    """Run the ordered, pure-until-publication migration planning stages."""

    source_payload = _read_index(root)
    inventory = _inventory_document(root, source_payload)
    source_rows = _split_source_rows(source_payload)
    mappings, status_document, status_payload = _load_status_map(status_map_path)
    migration_basis = {
        "tool_version": TOOL_VERSION,
        "root_identity": _root_identity(root)["sha256"],
        "source_index_sha256": inventory["index_sha256"],
        "source_inventory_sha256": inventory["inventory_sha256"],
        "status_map_sha256": sha256_bytes(status_payload),
    }
    migration_id = "agent-log-migration-" + sha256_bytes(
        _canonical_json_bytes(migration_basis)
    )[:24]
    markdown_by_path = {item["path"]: item for item in inventory["markdown"]}
    row_plans, grouped = classify_source_rows(root, source_rows, mappings)
    canonical_sources = select_canonical_sources(
        root, grouped, row_plans, markdown_by_path
    )
    canonical_sources, body_alias_paths = deduplicate_body_aliases(
        root, canonical_sources, row_plans, markdown_by_path
    )
    orphan_entries, body_resolutions = build_body_resolutions(
        inventory,
        grouped,
        canonical_sources,
        row_plans,
        markdown_by_path,
        body_alias_paths,
    )
    rows = [row_plans[row["source_line"]] for row in source_rows]
    unresolved_count = sum(
        1 for row in rows if row["classification"] == "unresolved"
    )
    counts = Counter(row["classification"] for row in rows)
    counts["orphan_markdown"] = len(orphan_entries)
    counts["legacy_import_markdown"] = sum(
        1
        for item in orphan_entries
        if item["disposition"] == "bind_as_legacy_import"
    )
    counts["body_alias_markdown"] = len(body_alias_paths)
    records = (
        build_canonical_records(
            root,
            migration_id,
            canonical_sources,
            row_plans,
            markdown_by_path,
            orphan_entries,
        )
        if unresolved_count == 0
        else []
    )
    after_payload, unresolved_count = finalize_record_identifiers(
        records, unresolved_count, counts
    )
    plan = build_plan_document(
        root=root,
        migration_id=migration_id,
        inventory=inventory,
        status_map_path=status_map_path,
        status_document=status_document,
        status_payload=status_payload,
        rows=rows,
        orphan_entries=orphan_entries,
        body_resolutions=body_resolutions,
        counts=counts,
        unresolved_count=unresolved_count,
        after_payload=after_payload,
        record_count=len(records),
    )
    return plan, after_payload
