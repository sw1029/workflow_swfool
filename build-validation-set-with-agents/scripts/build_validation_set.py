#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


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


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_items(records: list[dict[str, Any]], set_id: str, source_class_default: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        item = dict(record)
        item.setdefault("item_id", f"{set_id}-item-{index:04d}")
        item.setdefault("source_class", source_class_default)
        item.setdefault("evidence_status", "candidate")
        item.setdefault("task_family", "unspecified")
        result.append(item)
    return result


def source_class_distribution(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("source_class") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def build(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    set_id = args.set_id
    set_root = root / args.output_root / set_id
    raw_items = read_jsonl(Path(args.items).resolve()) if args.items else []
    items = normalize_items(raw_items, set_id, args.source_class_default)

    items_path = set_root / "validation_set_items.jsonl"
    labels_path = set_root / "validation_set_labels.jsonl"
    oracle_path = set_root / "oracle_manifest.json"
    split_path = set_root / "split_manifest.json"
    leakage_path = set_root / "leakage_report.json"
    manifest_path = set_root / "validation_set_manifest.json"

    write_jsonl(items_path, items)
    write_jsonl(labels_path, [])
    write_json(
        oracle_path,
        {
            "validation_set_id": set_id,
            "oracle_count": 1,
            "oracles": [
                {
                    "oracle_id": f"{set_id}-oracle-required-fields",
                    "oracle_type": "deterministic",
                    "target": "item",
                    "description": "Each item carries required traceability fields.",
                    "required_fields": ["item_id", "source_class", "evidence_status"],
                }
            ],
        },
    )
    write_json(
        split_path,
        {
            "validation_set_id": set_id,
            "sealed_holdout_status": args.sealed_holdout_status,
            "label_visibility_policy": "dev labels visible; sealed holdout labels must not be passed to implementation workers",
            "splits": {"dev": [str(item["item_id"]) for item in items]},
        },
    )
    write_json(
        leakage_path,
        {
            "validation_set_id": set_id,
            "status": "not_run",
            "findings": [],
            "message": "Run leakage_check.py before readiness claims.",
        },
    )
    manifest = {
        "created_at": now_iso(),
        "validation_set_id": set_id,
        "task_id": args.task_id,
        "cycle_id": args.cycle_id,
        "validation_set_status": "candidate_only" if args.candidate_only else "partial",
        "quality_tier": args.quality_tier,
        "not_gold": args.not_gold,
        "item_count": len(items),
        "label_count": 0,
        "oracle_count": 1,
        "source_class_distribution": source_class_distribution(items),
        "items_path": items_path.relative_to(root).as_posix(),
        "labels_path": labels_path.relative_to(root).as_posix(),
        "oracle_manifest_path": oracle_path.relative_to(root).as_posix(),
        "split_manifest_path": split_path.relative_to(root).as_posix(),
        "leakage_report_path": leakage_path.relative_to(root).as_posix(),
        "no_overclaim_flags": ["not_gold", "candidate_only"] if args.not_gold else [],
        "forbidden_promotions": ["fixture_to_sampled_real", "metadata_to_gold"],
    }
    write_json(manifest_path, manifest)
    return {"status": "ok", "validation_set_id": set_id, "validation_set_root": set_root.relative_to(root).as_posix(), "manifest_path": manifest_path.relative_to(root).as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package bounded candidate JSONL into a validation-set directory.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--set-id", required=True)
    parser.add_argument("--task-id")
    parser.add_argument("--cycle-id")
    parser.add_argument("--items", help="Candidate item JSONL. Records are copied without raw-body expansion.")
    parser.add_argument("--output-root", default=".validation/sets")
    parser.add_argument("--quality-tier", choices=("candidate", "silver", "human_review_required", "gold"), default="candidate")
    parser.add_argument("--not-gold", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--candidate-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--source-class-default", default="generated_candidate")
    parser.add_argument("--sealed-holdout-status", choices=("true_sealed", "quasi_sealed", "not_sealed", "not_applicable"), default="not_applicable")
    args = parser.parse_args(argv)
    json.dump(build(args), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
