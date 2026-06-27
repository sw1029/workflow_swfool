#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


FORBIDDEN_RAW_FIELDS = {"raw_body", "provider_body", "full_text", "source_text", "document_body"}


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


def duplicate_values(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    values = [str(record.get(field)) for record in records if record.get(field)]
    return [{"value": value, "count": count} for value, count in Counter(values).items() if count > 1]


def analyze(items: list[dict[str, Any]], labels: list[dict[str, Any]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    item_ids = {str(item.get("item_id")) for item in items if item.get("item_id")}
    for field in ("item_id", "source_hash", "preimage_hash"):
        duplicates = duplicate_values(items, field)
        if duplicates:
            findings.append({"severity": "block" if field == "item_id" else "warn", "code": f"duplicate_{field}", "evidence": duplicates[:20]})
    missing_targets = [label.get("label_id") or index for index, label in enumerate(labels, start=1) if str(label.get("item_id")) not in item_ids]
    if missing_targets:
        findings.append({"severity": "block", "code": "label_references_missing_item", "evidence": missing_targets[:20]})
    forbidden = walk_forbidden({"items": items, "labels": labels})
    if forbidden:
        findings.append({"severity": "block", "code": "raw_body_field_persisted", "evidence": forbidden[:20]})
    for item in items:
        source_class = str(item.get("source_class") or "")
        evidence_status = str(item.get("evidence_status") or "")
        if source_class in {"test_fixture", "synthetic_fixture", "sampled_real_metadata", "local_dataset_candidate"} and evidence_status in {"sampled_real_positive_evidence", "real_reviewed_work", "gold"}:
            findings.append({"severity": "block", "code": "source_class_promotion_violation", "item_id": item.get("item_id"), "source_class": source_class, "evidence_status": evidence_status})
    status = "block" if any(item["severity"] == "block" for item in findings) else "warn" if findings else "ok"
    return {"status": status, "item_count": len(items), "label_count": len(labels), "findings": findings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check validation set items/labels for leakage and source-class violations.")
    parser.add_argument("--items", required=True)
    parser.add_argument("--labels")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = analyze(read_jsonl(Path(args.items)), read_jsonl(Path(args.labels)) if args.labels else [])
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 2 if result["status"] == "block" else 0


if __name__ == "__main__":
    raise SystemExit(main())
