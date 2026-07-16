"""Independent orphan, resolution, and count verification."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .core import (
    _canonical_json,
    _is_int,
    _require,
    _sha256,
    _source_rows,
    _status_mappings,
)

from .source_evidence import (
    _prepare_inventory,
    _recompute_canonical_rows,
    _verify_plan_rows,
)


def _verify_orphans(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    inventory_by_path: dict[str, dict[str, Any]],
    path_rows: dict[str, list[dict[str, Any]]],
    canonical_by_line: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    orphans = plan.get("orphans")
    _require(
        isinstance(orphans, list) and orphans == manifest.get("orphans"),
        "plan and manifest orphan inventories differ",
    )
    _require(
        orphans
        == sorted(
            orphans,
            key=lambda entry: entry.get("path", "") if isinstance(entry, dict) else "",
        ),
        "orphan inventory order is not independently reproducible",
    )
    orphan_by_path = {
        entry.get("path"): entry for entry in orphans if isinstance(entry, dict)
    }
    _require(len(orphan_by_path) == len(orphans), "orphan inventory has duplicate paths")
    _require(
        set(orphan_by_path) == set(inventory_by_path) - set(path_rows),
        "orphan disposition is missing or stale",
    )
    targets = {
        inventory_by_path[entry["source_path"]]["body_sha256"]: entry["source_path"]
        for entry in canonical_by_line.values()
    }
    for path in sorted(orphan_by_path):
        entry = orphan_by_path[path]
        inventory_entry = inventory_by_path[path]
        _require(
            entry.get("body_sha256") == inventory_entry.get("body_sha256")
            and _is_int(entry.get("size"))
            and entry.get("size") == inventory_entry.get("size"),
            f"orphan body binding mismatch: {path}",
        )
        _require(
            entry.get("structured_fields_status") == "not_evaluated",
            f"orphan structured-fields status mismatch: {path}",
        )
        target = targets.get(entry["body_sha256"])
        if target is None:
            _require(
                entry.get("disposition") == "bind_as_legacy_import"
                and entry.get("canonical_target_path") is None
                and set(entry)
                == {
                    "path",
                    "body_sha256",
                    "size",
                    "disposition",
                    "structured_fields_status",
                },
                f"independent orphan disposition mismatch: {path}",
            )
            targets[entry["body_sha256"]] = path
        else:
            _require(
                entry.get("disposition") == "quarantine_nonlog_body"
                and entry.get("canonical_target_path") == target
                and entry.get("alias_reason")
                == "byte_identical_body_different_path"
                and set(entry)
                == {
                    "path",
                    "body_sha256",
                    "size",
                    "disposition",
                    "structured_fields_status",
                    "canonical_target_path",
                    "alias_reason",
                },
                f"independent orphan disposition mismatch: {path}",
            )
    return orphans, orphan_by_path

def _verify_resolutions(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    inventory_by_path: dict[str, dict[str, Any]],
    path_rows: dict[str, list[dict[str, Any]]],
    orphan_by_path: dict[str, dict[str, Any]],
) -> None:
    resolutions = plan.get("body_resolutions")
    _require(
        isinstance(resolutions, list)
        and resolutions == manifest.get("markdown_resolutions"),
        "plan and manifest body resolutions differ",
    )
    _require(
        resolutions
        == sorted(
            resolutions,
            key=lambda entry: entry.get("path", "") if isinstance(entry, dict) else "",
        ),
        "body resolution order is not independently reproducible",
    )
    by_path = {
        entry.get("path"): entry for entry in resolutions if isinstance(entry, dict)
    }
    _require(len(by_path) == len(resolutions), "body resolutions have duplicate paths")
    _require(set(by_path) == set(inventory_by_path), "body resolution accounting is incomplete")
    for path, resolution in by_path.items():
        source = inventory_by_path[path]
        _require(
            set(resolution) == {"path", "body_sha256", "size", "disposition"}
            and resolution.get("body_sha256") == source.get("body_sha256")
            and _is_int(resolution.get("size"))
            and resolution.get("size") == source.get("size"),
            f"body resolution drift: {path}",
        )
        if path in orphan_by_path:
            expected = orphan_by_path[path]["disposition"]
        elif any(row["classification"] == "canonical_log" for row in path_rows[path]):
            expected = "bind_existing_body"
        else:
            expected = "retain_as_alias_evidence"
        _require(
            resolution.get("disposition") == expected,
            f"body resolution disposition mismatch: {path}",
        )

def _verified_counts(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    plan_rows: list[dict[str, Any]],
    orphans: list[dict[str, Any]],
    counts: Counter[str],
) -> dict[str, int]:
    counts["orphan_markdown"] = len(orphans)
    counts["legacy_import_markdown"] = sum(
        entry["disposition"] == "bind_as_legacy_import" for entry in orphans
    )
    alias_paths = {
        entry["source_path"]
        for entry in plan_rows
        if entry.get("classification") == "duplicate_alias"
        and entry.get("source_path") != entry.get("canonical_target_path")
    }
    alias_paths.update(
        entry["path"]
        for entry in orphans
        if entry.get("disposition") == "quarantine_nonlog_body"
    )
    counts["body_alias_markdown"] = len(alias_paths)
    expected = dict(sorted(counts.items()))
    for observed, label in (
        (plan.get("classification_counts"), "plan"),
        (manifest.get("classification_counts"), "manifest"),
    ):
        _require(
            isinstance(observed, dict)
            and all(
                isinstance(key, str) and _is_int(value)
                for key, value in observed.items()
            ),
            f"{label} classification counts are malformed",
        )
        _require(observed == expected, f"{label} classification counts mismatch")
    _require(
        _is_int(plan.get("unresolved_count"))
        and plan["unresolved_count"] == 0
        and _is_int(manifest.get("unresolved_count"))
        and manifest["unresolved_count"] == 0,
        "unresolved migration cannot verify",
    )
    return expected

def _verify_rows_and_inventory(
    *,
    root: Path,
    source_payload: bytes,
    plan: dict[str, Any],
    manifest: dict[str, Any],
    status_map: dict[str, Any],
    actual_markdown: list[dict[str, Any]],
) -> dict[str, Any]:
    source_rows = _source_rows(source_payload)
    source_by_line = {row["source_line"]: row for row in source_rows}
    plan_rows = plan.get("rows")
    _require(isinstance(plan_rows, list), "plan rows are missing")
    _require(
        all(
            isinstance(entry, dict) and _is_int(entry.get("source_line"))
            for entry in plan_rows
        )
        and plan_rows == sorted(plan_rows, key=lambda entry: entry["source_line"]),
        "plan source-row order is not independently reproducible",
    )
    _require(len(plan_rows) == len(source_rows), "plan source-row accounting mismatch")
    _require(
        plan_rows == manifest.get("source_rows"),
        "plan and manifest source classifications differ",
    )
    inventory, inventory_by_path, actual_by_path = _prepare_inventory(
        manifest, actual_markdown
    )
    counts, path_rows = _verify_plan_rows(
        source_by_line,
        plan_rows,
        _status_mappings(status_map),
        inventory_by_path,
    )
    canonical = _recompute_canonical_rows(
        root, path_rows, source_by_line, inventory_by_path
    )
    orphans, orphan_by_path = _verify_orphans(
        plan, manifest, inventory_by_path, path_rows, canonical
    )
    _verify_resolutions(
        plan, manifest, inventory_by_path, path_rows, orphan_by_path
    )
    expected_counts = _verified_counts(
        plan, manifest, plan_rows, orphans, counts
    )
    inventory_basis = {
        "index_sha256": _sha256(source_payload),
        "index_size": len(source_payload),
        "source_row_count": len(source_rows),
        "markdown": inventory,
    }
    inventory_sha = _sha256(_canonical_json(inventory_basis))
    _require(
        plan.get("source_inventory_sha256") == inventory_sha
        and manifest.get("source_inventory_sha256") == inventory_sha,
        "source inventory hash mismatch",
    )
    _require(
        _is_int(plan.get("source_markdown_count"))
        and plan["source_markdown_count"] == len(inventory),
        "plan Markdown count mismatch",
    )
    return {
        "source_rows": source_rows,
        "inventory_sha256": inventory_sha,
        "inventory_by_path": inventory_by_path,
        "canonical_by_line": canonical,
        "orphans": orphans,
        "counts": expected_counts,
        "actual_markdown": actual_by_path,
    }
