#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ALLOWED_SOURCE_CLASSES = {
    "test_fixture",
    "synthetic_fixture",
    "sampled_real_metadata",
    "sampled_real_positive_evidence",
    "real_reviewed_work",
    "local_dataset_candidate",
    "external_metadata",
    "generated_candidate",
}
QUALITY_TIERS = {"candidate", "silver", "human_review_required", "gold"}
FORBIDDEN_RAW_FIELDS = {"raw_body", "provider_body", "full_text", "source_text", "document_body"}


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
    return records


def resolve(root: Path, base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = root / path
    return candidate if candidate.exists() else base / path


def add(findings: list[dict[str, Any]], severity: str, code: str, message: str, evidence: Any = None) -> None:
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if evidence is not None:
        item["evidence"] = evidence
    findings.append(item)


def walk_forbidden(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if key in FORBIDDEN_RAW_FIELDS and item not in (None, "", [], {}):
                found.append(child)
            found.extend(walk_forbidden(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(walk_forbidden(item, f"{path}[{index}]"))
    return found


def positive_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def validate_manifest(manifest: dict[str, Any], findings: list[dict[str, Any]]) -> None:
    for field in ("validation_set_id", "validation_set_status", "quality_tier", "not_gold", "item_count", "label_count", "oracle_count", "items_path", "labels_path", "oracle_manifest_path", "split_manifest_path", "leakage_report_path"):
        if field not in manifest or manifest.get(field) in (None, "", [], {}):
            if field == "not_gold" and manifest.get(field) is False:
                continue
            add(findings, "block", "missing_manifest_field", f"Manifest is missing `{field}`.", {"field": field})
    quality_tier = str(manifest.get("quality_tier") or "")
    if quality_tier and quality_tier not in QUALITY_TIERS:
        add(findings, "block", "invalid_quality_tier", "Quality tier is not recognized.", {"quality_tier": quality_tier})
    if quality_tier == "gold":
        human_reviewed = positive_int(manifest.get("human_reviewed_count")) > 0
        deterministic_authoritative = bool(manifest.get("fully_deterministic_authoritative_oracle"))
        if not human_reviewed and not deterministic_authoritative:
            add(findings, "block", "gold_without_authoritative_evidence", "`quality_tier: gold` requires human-reviewed or fully deterministic authoritative evidence.")


def validate_items(items: list[dict[str, Any]], findings: list[dict[str, Any]]) -> None:
    ids = [str(item.get("item_id")) for item in items if item.get("item_id")]
    duplicate_ids = [{"item_id": key, "count": count} for key, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        add(findings, "block", "duplicate_item_id", "Item IDs must be unique.", duplicate_ids[:20])
    for index, item in enumerate(items, start=1):
        item_id = item.get("item_id") or f"item[{index}]"
        for field in ("item_id", "source_class", "evidence_status"):
            if item.get(field) in (None, "", [], {}):
                add(findings, "block", "missing_item_field", f"Validation item is missing `{field}`.", {"item_id": item_id, "field": field})
        source_class = str(item.get("source_class") or "")
        if source_class and source_class not in ALLOWED_SOURCE_CLASSES:
            add(findings, "warn", "unknown_source_class", "Source class is not in the default vocabulary.", {"item_id": item_id, "source_class": source_class})
        evidence_status = str(item.get("evidence_status") or "")
        if source_class in {"test_fixture", "synthetic_fixture", "sampled_real_metadata", "local_dataset_candidate"} and evidence_status in {"sampled_real_positive_evidence", "real_reviewed_work", "gold"}:
            add(findings, "block", "source_class_promotion_violation", "Item evidence status promotes a fixture/metadata class into sampled-real or gold evidence.", {"item_id": item_id, "source_class": source_class, "evidence_status": evidence_status})


def validate_labels(labels: list[dict[str, Any]], item_ids: set[str], findings: list[dict[str, Any]]) -> None:
    for index, label in enumerate(labels, start=1):
        label_id = label.get("label_id") or f"label[{index}]"
        item_id = str(label.get("item_id") or "")
        if not item_id:
            add(findings, "block", "label_missing_item_id", "Label record is missing `item_id`.", {"label_id": label_id})
        elif item_id not in item_ids:
            add(findings, "block", "label_references_missing_item", "Label references an item that does not exist.", {"label_id": label_id, "item_id": item_id})
        if label.get("label_type") == "human_reviewed" and not label.get("human_reviewer_ref"):
            add(findings, "warn", "human_reviewed_without_reviewer_ref", "Human-reviewed labels should name bounded reviewer evidence.", {"label_id": label_id})


def validate_counts(manifest: dict[str, Any], items: list[dict[str, Any]], labels: list[dict[str, Any]], oracle_manifest: dict[str, Any], findings: list[dict[str, Any]]) -> None:
    expected = {
        "item_count": len(items),
        "label_count": len(labels),
        "oracle_count": len(oracle_manifest.get("oracles") or []) if isinstance(oracle_manifest.get("oracles"), list) else positive_int(oracle_manifest.get("oracle_count")),
    }
    for field, actual in expected.items():
        if field in manifest and positive_int(manifest.get(field)) != actual:
            add(findings, "warn", "manifest_count_mismatch", f"`{field}` does not match loaded files.", {"manifest": manifest.get(field), "actual": actual})


def validate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else (Path(args.set_root).resolve() / "validation_set_manifest.json")
    manifest = read_json(manifest_path)
    base = manifest_path.parent
    findings: list[dict[str, Any]] = []
    validate_manifest(manifest, findings)
    items_path = resolve(root, base, manifest.get("items_path"))
    labels_path = resolve(root, base, manifest.get("labels_path"))
    oracle_path = resolve(root, base, manifest.get("oracle_manifest_path"))
    split_path = resolve(root, base, manifest.get("split_manifest_path"))
    leakage_path = resolve(root, base, manifest.get("leakage_report_path"))
    for label, path in (("items_path", items_path), ("labels_path", labels_path), ("oracle_manifest_path", oracle_path), ("split_manifest_path", split_path), ("leakage_report_path", leakage_path)):
        if path is None or not path.is_file():
            add(findings, "block", "manifest_path_missing", f"`{label}` does not resolve to a file.", {"path": str(path) if path else None})
    items = read_jsonl(items_path) if items_path else []
    labels = read_jsonl(labels_path) if labels_path else []
    oracle_manifest = read_json(oracle_path) if oracle_path else {}
    split_manifest = read_json(split_path) if split_path else {}
    leakage_report = read_json(leakage_path) if leakage_path else {}
    forbidden_paths = walk_forbidden({"manifest": manifest, "items": items, "labels": labels, "oracles": oracle_manifest, "splits": split_manifest})
    if forbidden_paths:
        add(findings, "block", "raw_body_field_persisted", "Durable validation artifacts contain raw body fields.", forbidden_paths[:20])
    validate_items(items, findings)
    validate_labels(labels, {str(item.get("item_id")) for item in items if item.get("item_id")}, findings)
    validate_counts(manifest, items, labels, oracle_manifest, findings)
    if leakage_report.get("status") == "block":
        add(findings, "block", "leakage_report_blocking", "Leakage report contains blocking findings.", leakage_report.get("findings"))
    if split_manifest.get("sealed_holdout_labels_exposed") is True:
        add(findings, "block", "sealed_holdout_labels_exposed", "Sealed holdout labels were exposed.")
    status = "block" if any(item["severity"] == "block" for item in findings) else "warn" if findings else "ok"
    return {
        "status": status,
        "manifest_path": str(manifest_path),
        "validation_set_id": manifest.get("validation_set_id"),
        "item_count": len(items),
        "label_count": len(labels),
        "oracle_count": len(oracle_manifest.get("oracles") or []) if isinstance(oracle_manifest.get("oracles"), list) else positive_int(oracle_manifest.get("oracle_count")),
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
