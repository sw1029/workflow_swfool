#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


FORBIDDEN_RAW_FIELDS = {"raw_body", "provider_body", "full_text", "source_text", "document_body"}


def normalized_field_name(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).casefold().replace("-", "_")


def read_jsonl(path: Path, artifact: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    if not path.is_file():
        return records, [{"severity": "block", "code": "artifact_missing", "artifact": artifact, "path": str(path)}]
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    findings.append({"severity": "block", "code": "invalid_jsonl_record", "artifact": artifact, "line": line_number, "error": str(exc)})
                    continue
                if not isinstance(value, dict):
                    findings.append({"severity": "block", "code": "invalid_jsonl_record_type", "artifact": artifact, "line": line_number})
                    continue
                records.append(value)
    except (OSError, UnicodeError) as exc:
        findings.append({"severity": "block", "code": "unreadable_artifact", "artifact": artifact, "path": str(path), "error": str(exc)})
    return records, findings


def walk_forbidden(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if normalized_field_name(str(key)) in FORBIDDEN_RAW_FIELDS:
                found.append(child)
            found.extend(walk_forbidden(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(walk_forbidden(item, f"{path}[{index}]"))
    return found


def duplicate_values(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    values = [str(record.get(field)) for record in records if record.get(field)]
    return [{"value": value, "count": count} for value, count in Counter(values).items() if count > 1]


def analyze(
    items: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    input_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    findings = list(input_findings or [])
    if not items and not labels and not any(finding.get("severity") == "block" for finding in findings):
        return {
            "status": "not_evaluated",
            "execution_status": "not_evaluated",
            "item_count": 0,
            "label_count": len(labels),
            "findings": [{"severity": "warn", "code": "no_items_to_check"}],
        }
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
    return {"status": status, "execution_status": "completed", "item_count": len(items), "label_count": len(labels), "findings": findings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check validation-set items/labels for leakage and source-class violations.")
    parser.add_argument("--items", required=True)
    parser.add_argument("--labels")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    items, item_findings = read_jsonl(Path(args.items), "items")
    labels: list[dict[str, Any]] = []
    label_findings: list[dict[str, Any]] = []
    if args.labels:
        labels, label_findings = read_jsonl(Path(args.labels), "labels")
    result = analyze(items, labels, item_findings + label_findings)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if result["status"] == "block":
        return 2
    if result["status"] == "not_evaluated":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
