#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

from validation_set_contract import MANIFEST_SCHEMA_VERSION, ORACLE_RESULTS_SCHEMA_VERSION, atomic_write_json, atomic_write_jsonl, sha256_file


FORBIDDEN_RAW_FIELDS = {"raw_body", "provider_body", "full_text", "source_text", "document_body"}


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"candidate item file does not exist: {path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"candidate item JSONL record {line_number} is not an object")
            records.append(value)
    return records


def write_json(path: Path, data: dict[str, Any], *, root: Path) -> None:
    atomic_write_json(path, data, root=root)


def write_jsonl(path: Path, records: list[dict[str, Any]], *, root: Path) -> None:
    atomic_write_jsonl(path, records, root=root)


def normalize_items(records: list[dict[str, Any]], set_id: str, source_class_default: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        item = dict(record)
        item.setdefault("item_id", f"{set_id}-item-{index:04d}")
        item.setdefault("source_class", source_class_default)
        item.setdefault("evidence_status", "candidate")
        item.setdefault("task_family", "unspecified")
        source_ref = item.get("source_ref")
        if "source_binding_type" not in item:
            if isinstance(item.get("source_attestation"), dict):
                item["source_binding_type"] = "authoritative_attestation"
            elif isinstance(source_ref, str) and source_ref and not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", source_ref):
                item["source_binding_type"] = "local_file"
            else:
                item["source_binding_type"] = "opaque_candidate"
        result.append(item)
    return result


def source_class_distribution(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("source_class") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def normalized_field_name(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).casefold().replace("-", "_")


def forbidden_paths(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if normalized_field_name(str(key)) in FORBIDDEN_RAW_FIELDS:
                found.append(child)
            found.extend(forbidden_paths(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(forbidden_paths(item, f"{path}[{index}]"))
    return found


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def validate_custom_oracles(document: dict[str, Any], set_id: str, items: list[dict[str, Any]]) -> None:
    if document.get("validation_set_id") != set_id:
        raise ValueError("custom oracle manifest must use the requested validation_set_id")
    oracles = document.get("oracles")
    if not isinstance(oracles, list) or not oracles:
        raise ValueError("custom oracle manifest requires a non-empty oracles list")
    oracle_ids = {
        oracle.get("oracle_id")
        for oracle in oracles
        if isinstance(oracle, dict) and isinstance(oracle.get("oracle_id"), str) and oracle.get("oracle_id")
    }
    if len(oracle_ids) != len(oracles):
        raise ValueError("custom oracle manifest requires unique non-empty oracle_id values")
    unresolved = sorted(
        {
            str(oracle_id)
            for item in items
            for oracle_id in (item.get("oracle_ids") or [])
            if oracle_id not in oracle_ids
        }
    )
    if unresolved:
        raise ValueError(f"candidate items reference unknown custom oracles: {unresolved[:5]}")
    document["oracle_count"] = len(oracles)


def validate_custom_split(document: dict[str, Any], set_id: str, items: list[dict[str, Any]]) -> None:
    if document.get("validation_set_id") != set_id:
        raise ValueError("custom split manifest must use the requested validation_set_id")
    splits = document.get("splits")
    if not isinstance(splits, dict) or not splits:
        raise ValueError("custom split manifest requires a non-empty splits mapping")
    expected = {str(item["item_id"]) for item in items}
    members: list[str] = []
    for split_name, values in splits.items():
        if not isinstance(split_name, str) or not split_name or not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
            raise ValueError("custom split entries must map non-empty names to item ID lists")
        members.extend(values)
    if len(members) != len(set(members)) or set(members) != expected:
        raise ValueError("custom split manifest must assign every candidate item exactly once")


def build(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    set_id = args.set_id
    if not set_id.strip() or Path(set_id).name != set_id or set_id in {".", ".."}:
        raise ValueError("set ID must be a non-empty single path component")
    set_root = (root / args.output_root / set_id).resolve()
    try:
        set_root.relative_to(root)
    except ValueError as exc:
        raise ValueError("output root/set ID escapes the declared root") from exc
    if args.quality_tier == "gold":
        raise ValueError("the candidate packager cannot create gold evidence; add concrete human/authoritative evidence through the reviewed build workflow")
    raw_items = read_jsonl(Path(args.items).resolve()) if args.items else []
    items = normalize_items(raw_items, set_id, args.source_class_default)
    raw_fields = forbidden_paths(items)
    if raw_fields:
        raise ValueError(f"candidate items contain forbidden raw-body fields: {', '.join(raw_fields[:5])}")
    missing_trace = [item.get("item_id") for item in items if not item.get("source_ref") and not item.get("source_hash")]
    if missing_trace:
        raise ValueError(f"candidate items require source_ref or source_hash: {missing_trace[:5]}")

    items_path = set_root / "validation_set_items.jsonl"
    labels_path = set_root / "validation_set_labels.jsonl"
    oracle_path = set_root / "oracle_manifest.json"
    oracle_results_path = set_root / "oracle_results.json"
    split_path = set_root / "split_manifest.json"
    leakage_path = set_root / "leakage_report.json"
    manifest_path = set_root / "validation_set_manifest.json"

    custom_oracle_ids = sorted({str(value) for item in items for value in (item.get("oracle_ids") or [])})
    if args.oracle_manifest:
        oracle_document = read_json_object(Path(args.oracle_manifest).resolve(), "custom oracle manifest")
        validate_custom_oracles(oracle_document, set_id, items)
    else:
        if custom_oracle_ids:
            raise ValueError("custom item oracle_ids require --oracle-manifest so the scaffold cannot create unresolved references")
        default_oracle_id = f"{set_id}-oracle-required-fields"
        for item in items:
            item["oracle_ids"] = [default_oracle_id]
        oracle_document = {
            "validation_set_id": set_id,
            "oracle_count": 1,
            "oracles": [
                {
                    "oracle_id": default_oracle_id,
                    "oracle_type": "deterministic",
                    "target": "item",
                    "description": "Each item carries required traceability fields.",
                    "required_fields": ["item_id", "source_class", "evidence_status", "task_family"],
                }
            ],
        }
    if args.split_manifest:
        split_document = read_json_object(Path(args.split_manifest).resolve(), "custom split manifest")
        validate_custom_split(split_document, set_id, items)
    else:
        split_document = {
            "validation_set_id": set_id,
            "sealed_holdout_status": args.sealed_holdout_status,
            "label_visibility_policy": "dev labels visible; sealed holdout labels must not be passed to implementation workers",
            "splits": {"dev": [str(item["item_id"]) for item in items]},
        }

    write_jsonl(items_path, items, root=root)
    write_jsonl(labels_path, [], root=root)
    write_json(oracle_path, oracle_document, root=root)
    write_json(split_path, split_document, root=root)
    write_json(
        oracle_results_path,
        {
            "oracle_results_schema_version": ORACLE_RESULTS_SCHEMA_VERSION,
            "runner": "run_validation_oracles.py",
            "validation_set_id": set_id,
            "status": "not_evaluated",
            "execution_status": "not_evaluated",
            "items_sha256": sha256_file(items_path),
            "oracle_manifest_sha256": sha256_file(oracle_path),
            "item_count": len(items),
            "oracle_count": len(oracle_document["oracles"]),
            "runnable_oracle_count": 0,
            "required_pair_count": 0,
            "executed_pair_count": 0,
            "unsupported_pair_count": 0,
            "unsupported_pairs": [],
            "result_count": 0,
            "failed_count": 0,
            "not_evaluated_reasons": ["candidate_scaffold_requires_oracle_run"],
            "results": [],
        },
        root=root,
    )
    write_json(
        leakage_path,
        {
            "validation_set_id": set_id,
            "status": "not_run",
            "execution_status": "not_evaluated",
            "item_count": len(items),
            "label_count": 0,
            "findings": [],
            "message": "Run leakage_check.py before readiness claims.",
        },
        root=root,
    )
    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "created_at": now_iso(),
        "validation_set_id": set_id,
        "task_id": args.task_id,
        "cycle_id": args.cycle_id,
        "validation_set_status": "candidate_only" if args.candidate_only else "partial",
        "quality_tier": args.quality_tier,
        "not_gold": args.not_gold,
        "item_count": len(items),
        "label_count": 0,
        "oracle_count": len(oracle_document["oracles"]),
        "source_class_distribution": source_class_distribution(items),
        "items_path": items_path.relative_to(root).as_posix(),
        "labels_path": labels_path.relative_to(root).as_posix(),
        "oracle_manifest_path": oracle_path.relative_to(root).as_posix(),
        "oracle_results_path": oracle_results_path.relative_to(root).as_posix(),
        "split_manifest_path": split_path.relative_to(root).as_posix(),
        "leakage_report_path": leakage_path.relative_to(root).as_posix(),
        "no_overclaim_flags": ["not_gold", "candidate_only"] if args.not_gold else [],
        "forbidden_promotions": ["fixture_to_sampled_real", "metadata_to_gold"],
    }
    write_json(manifest_path, manifest, root=root)
    return {
        "artifact_kind": "candidate_scaffold",
        "status": manifest["validation_set_status"],
        "readiness": "candidate" if items else "not_evaluated",
        "validation_set_id": set_id,
        "validation_set_root": set_root.relative_to(root).as_posix(),
        "manifest_path": manifest_path.relative_to(root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a candidate-only validation-set scaffold; use finalize_validation_set.py for promotion.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--set-id", required=True)
    parser.add_argument("--task-id")
    parser.add_argument("--cycle-id")
    parser.add_argument("--items", help="Candidate item JSONL. Records are copied without raw-body expansion.")
    parser.add_argument("--oracle-manifest", help="Plan-provided oracle manifest. Required when items already name custom oracle_ids.")
    parser.add_argument("--split-manifest", help="Plan-provided split manifest assigning every item exactly once.")
    parser.add_argument("--output-root", default=".validation/sets")
    parser.add_argument("--quality-tier", choices=("candidate", "silver", "human_review_required", "gold"), default="candidate")
    parser.add_argument("--not-gold", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--candidate-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--source-class-default", default="generated_candidate")
    parser.add_argument("--sealed-holdout-status", choices=("true_sealed", "quasi_sealed", "not_sealed", "not_applicable"), default="not_applicable")
    args = parser.parse_args(argv)
    try:
        result = build(args)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        json.dump({"status": "block", "error": str(exc)}, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
