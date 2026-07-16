#!/usr/bin/env python3
"""Compose ordered validation-set checks and expose the validation CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .validation_common import (
    add,
    is_json_int,
    read_json,
    read_jsonl,
    resolve_manifest_path,
    validate_boolean_fields,
    walk_forbidden,
    within_root,
)
from .validation_records import (
    validate_items,
    validate_labels,
    validate_manifest,
    validate_oracles,
    validate_source_bindings,
)
from .validation_results import (
    validate_counts,
    validate_finalization_record,
    validate_gold,
    validate_oracle_results,
    validate_scenario_coverage,
    validate_split_manifest,
)
from .validation_set_contract import ARTIFACT_FIELDS, MANIFEST_SCHEMA_VERSION

def validate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    requested = Path(args.manifest) if args.manifest else Path(args.set_root) / "validation_set_manifest.json"
    requested = requested if requested.is_absolute() else root / requested
    manifest_path = within_root(root, requested)
    findings: list[dict[str, Any]] = []
    manifest_allowed = manifest_path is not None
    if manifest_path is None:
        add(findings, "block", "manifest_path_escape", "Manifest path escapes the declared root, including through a symlink.", {"path": str(requested)})
        manifest_path = requested.resolve(strict=False)
    if not manifest_allowed:
        manifest = {}
    elif not manifest_path.is_file():
        add(findings, "block", "manifest_file_missing", "Validation-set manifest does not exist.", {"path": str(manifest_path)})
        manifest = {}
    else:
        manifest = read_json(manifest_path, findings, "validation_set_manifest")
    base = manifest_path.parent
    strict_v2 = type(manifest.get("manifest_schema_version")) is int and manifest.get("manifest_schema_version") == MANIFEST_SCHEMA_VERSION
    legacy_manifest = manifest.get("manifest_schema_version") is None
    consumable = validate_manifest(manifest, findings)
    paths: dict[str, Path | None] = {}
    path_fields = ["items_path", "labels_path", "oracle_manifest_path", "split_manifest_path", "leakage_report_path"]
    if strict_v2 or "oracle_results_path" in manifest:
        path_fields.append("oracle_results_path")
    for field in path_fields:
        path = resolve_manifest_path(root, base, manifest.get(field), field, findings)
        paths[field] = path
        if path is None or not path.is_file():
            add(findings, "block", "manifest_path_missing", f"`{field}` does not resolve to a file.", {"path": str(path) if path else None})
    items = read_jsonl(paths["items_path"], findings, "validation_set_items") if paths["items_path"] and paths["items_path"].is_file() else []
    labels = read_jsonl(paths["labels_path"], findings, "validation_set_labels") if paths["labels_path"] and paths["labels_path"].is_file() else []
    oracle_manifest = read_json(paths["oracle_manifest_path"], findings, "oracle_manifest") if paths["oracle_manifest_path"] and paths["oracle_manifest_path"].is_file() else {}
    split_manifest = read_json(paths["split_manifest_path"], findings, "split_manifest") if paths["split_manifest_path"] and paths["split_manifest_path"].is_file() else {}
    leakage_report = read_json(paths["leakage_report_path"], findings, "leakage_report") if paths["leakage_report_path"] and paths["leakage_report_path"].is_file() else {}
    oracle_results_path = paths.get("oracle_results_path")
    oracle_results = read_json(oracle_results_path, findings, "oracle_results") if oracle_results_path and oracle_results_path.is_file() else {}
    durable = {"manifest": manifest, "items": items, "labels": labels, "oracles": oracle_manifest, "oracle_results": oracle_results, "splits": split_manifest, "leakage": leakage_report}
    forbidden_paths = walk_forbidden(durable)
    if forbidden_paths:
        add(findings, "block", "raw_body_field_persisted", "Durable validation artifacts contain forbidden raw-body field names, even if their current values are empty.", forbidden_paths[:20])
    validate_boolean_fields(durable, findings)
    item_ids = validate_items(items, manifest, findings)
    source_bindings_verified = validate_source_bindings(items, root=root, strict_v2=strict_v2, consumable=consumable, findings=findings)
    validate_labels(labels, item_ids, findings)
    oracles = validate_oracles(oracle_manifest, manifest, items, labels, findings)
    oracle_results_verified = validate_oracle_results(
        oracle_results,
        manifest=manifest,
        items=items,
        labels=labels,
        oracles=oracles,
        items_path=paths.get("items_path"),
        oracle_manifest_path=paths.get("oracle_manifest_path"),
        strict_v2=strict_v2,
        consumable=consumable,
        findings=findings,
    )
    validate_scenario_coverage(manifest, items, labels, oracles, oracle_results, root, consumable, findings)
    validate_split_manifest(split_manifest, manifest, item_ids, consumable, root, base, findings)
    validate_counts(manifest, items, labels, len(oracles), consumable, findings)
    leakage_status = leakage_report.get("status")
    leakage_execution = leakage_report.get("execution_status")
    if leakage_status == "block":
        add(findings, "block", "leakage_report_blocking", "Leakage report contains blocking findings.", leakage_report.get("findings"))
    if leakage_execution != "completed" or leakage_status not in {"ok", "warn", "block"}:
        add(findings, "block" if consumable else "warn", "leakage_not_evaluated", "Leakage checking must report `execution_status: completed` before the set is consumable.", {"status": leakage_status, "execution_status": leakage_execution})
    if leakage_execution == "completed":
        for field, actual in (("item_count", len(items)), ("label_count", len(labels))):
            if not is_json_int(leakage_report.get(field)) or leakage_report.get(field) != actual:
                add(findings, "block" if consumable else "warn", "leakage_count_mismatch", f"Leakage report `{field}` must match the bound records.", {"reported": leakage_report.get(field), "actual": actual})
    if consumable and leakage_status not in {"ok", "warn"}:
        add(findings, "block", "consumable_leakage_not_clear", "A consumable validation set requires a completed non-blocking leakage report.")
    if consumable and not source_bindings_verified:
        add(findings, "block", "consumable_source_bindings_unverified", "Every consumable item requires a verified local source binding or authoritative attestation.")
    if consumable and not oracle_results_verified:
        add(findings, "block", "consumable_oracle_results_unverified", "Consumable sets require current completed non-blocking oracle results.")
    if consumable:
        artifact_paths = {
            name: paths[field]
            for name, field in ARTIFACT_FIELDS.items()
            if paths.get(field) is not None and paths[field].is_file()
        }
        if len(artifact_paths) != len(ARTIFACT_FIELDS):
            add(findings, "block", "finalization_inputs_missing", "Complete schema-v2 sets require every finalization input artifact.")
        else:
            validate_finalization_record(manifest, artifact_paths, oracle_results, findings)
    validate_gold(manifest, labels, oracles, findings)
    status = "block" if any(item["severity"] == "block" for item in findings) else "warn" if findings else "ok"
    if consumable and status == "ok":
        readiness = "consumable"
    elif legacy_manifest and manifest.get("validation_set_status") == "complete" and status != "block":
        readiness = "migration_required"
    elif not consumable and status != "block":
        readiness = "candidate"
    else:
        readiness = "blocked"
    return {
        "status": status,
        "readiness": readiness,
        "manifest_path": str(manifest_path),
        "validation_set_id": manifest.get("validation_set_id"),
        "item_count": len(items),
        "label_count": len(labels),
        "oracle_count": len(oracles),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate validation-set manifest/files and no-overclaim guardrails.")
    parser.add_argument("--root", default=".")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--set-root")
    group.add_argument("--manifest")
    parser.add_argument("--warn-only", action="store_true")
    args = parser.parse_args(argv)
    result = validate(args)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if args.warn_only:
        return 0
    return 2 if result["status"] == "block" else 0


if __name__ == "__main__":
    raise SystemExit(main())
