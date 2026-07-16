#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .validation_set_contract import (
    ContractError,
    ORACLE_RESULTS_SCHEMA_VERSION,
    atomic_write_json,
    canonical_sha256,
    deterministic_result_record,
    required_item_oracle_pairs,
    resolve_root_file,
    resolve_root_path,
    sha256_file,
    within_root,
)


def read_json(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.is_file():
        return {}, [f"missing_file:{path}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, [f"invalid_json:{path}:{exc}"]
    if not isinstance(value, dict):
        return {}, [f"invalid_json_type:{path}"]
    return value, []


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.is_file():
        return records, [f"missing_file:{path}"]
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"invalid_jsonl:{path}:{line_number}:{exc}")
                    continue
                if not isinstance(value, dict):
                    errors.append(f"invalid_jsonl_type:{path}:{line_number}")
                    continue
                records.append(value)
    except (OSError, UnicodeError) as exc:
        errors.append(f"unreadable_file:{path}:{exc}")
    return records, errors


def validate_oracle(oracle: Any, index: int) -> list[str]:
    if not isinstance(oracle, dict):
        return [f"oracle_not_object:{index}"]
    failures: list[str] = []
    for field in ("oracle_id", "oracle_type", "target", "description"):
        if not isinstance(oracle.get(field), str) or not oracle[field].strip():
            failures.append(f"invalid_oracle_field:{index}:{field}")
    if oracle.get("oracle_type") != "deterministic":
        return failures
    for field in ("required_fields", "forbidden_fields"):
        value = oracle.get(field)
        if value is not None and (not isinstance(value, list) or any(not isinstance(entry, str) or not entry for entry in value)):
            failures.append(f"invalid_oracle_list:{index}:{field}")
    allowed_values = oracle.get("allowed_values")
    if allowed_values is not None and (not isinstance(allowed_values, dict) or any(not isinstance(values, list) for values in allowed_values.values())):
        failures.append(f"invalid_allowed_values:{index}")
    return failures


def analyze(items: list[dict[str, Any]], manifest: dict[str, Any], input_errors: list[str] | None = None) -> dict[str, Any]:
    errors = list(input_errors or [])
    declared_oracles = manifest.get("oracles")
    if not isinstance(declared_oracles, list):
        errors.append("oracle_manifest_missing_oracles_list")
        declared_oracles = []
    declared_count = manifest.get("oracle_count")
    if declared_count is not None and (type(declared_count) is not int or declared_count < 0 or declared_count != len(declared_oracles)):
        errors.append("oracle_count_mismatch")
    for index, oracle in enumerate(declared_oracles, start=1):
        errors.extend(validate_oracle(oracle, index))
    oracle_ids = [oracle.get("oracle_id") for oracle in declared_oracles if isinstance(oracle, dict) and isinstance(oracle.get("oracle_id"), str)]
    if len(oracle_ids) != len(set(oracle_ids)):
        errors.append("duplicate_oracle_id")
    if errors:
        return {
            "status": "failed",
            "execution_status": "failed",
            "item_count": len(items),
            "oracle_count": len(declared_oracles),
            "runnable_oracle_count": 0,
            "required_pair_count": 0,
            "executed_pair_count": 0,
            "unsupported_pair_count": 0,
            "unsupported_pairs": [],
            "result_count": 0,
            "failed_count": len(errors),
            "configuration_errors": errors,
            "results": [],
        }
    required_pairs = required_item_oracle_pairs(items, declared_oracles)
    runnable_pairs = [
        (item, oracle)
        for item, oracle in required_pairs
        if oracle.get("oracle_type") == "deterministic" and oracle.get("target") == "item"
    ]
    unsupported_pairs = [
        {
            "item_id": item.get("item_id") or item.get("id") or "unknown",
            "oracle_id": oracle.get("oracle_id"),
            "oracle_type": oracle.get("oracle_type"),
            "target": oracle.get("target"),
            "oracle_definition_sha256": canonical_sha256(oracle),
        }
        for item, oracle in required_pairs
        if not (oracle.get("oracle_type") == "deterministic" and oracle.get("target") == "item")
    ]
    runnable_oracle_ids = {str(oracle.get("oracle_id")) for _, oracle in runnable_pairs}
    if not items or not runnable_pairs:
        reasons = []
        if not items:
            reasons.append("no_items")
        if not declared_oracles:
            reasons.append("no_oracles")
        elif not runnable_pairs:
            reasons.append("no_supported_item_oracles")
        return {
            "status": "not_evaluated",
            "execution_status": "not_evaluated",
            "item_count": len(items),
            "oracle_count": len(declared_oracles),
            "runnable_oracle_count": len(runnable_oracle_ids),
            "required_pair_count": len(required_pairs),
            "executed_pair_count": 0,
            "unsupported_pair_count": len(unsupported_pairs),
            "unsupported_pairs": unsupported_pairs,
            "result_count": 0,
            "failed_count": 0,
            "not_evaluated_reasons": reasons,
            "results": [],
        }
    results = [deterministic_result_record(item, oracle) for item, oracle in runnable_pairs]
    failed = [item for item in results if item["status"] == "failed"]
    return {
        "status": "failed" if failed else "passed",
        "execution_status": "completed",
        "item_count": len(items),
        "oracle_count": len(declared_oracles),
        "runnable_oracle_count": len(runnable_oracle_ids),
        "required_pair_count": len(required_pairs),
        "executed_pair_count": len(results),
        "unsupported_pair_count": len(unsupported_pairs),
        "unsupported_pairs": unsupported_pairs,
        "result_count": len(results),
        "failed_count": len(failed),
        "results": results,
    }


def bind_result(
    result: dict[str, Any],
    *,
    validation_set_id: Any,
    items_path: Path,
    oracle_manifest_path: Path,
) -> dict[str, Any]:
    bound = dict(result)
    bound.update(
        {
            "oracle_results_schema_version": ORACLE_RESULTS_SCHEMA_VERSION,
            "runner": "run_validation_oracles.py",
            "validation_set_id": validation_set_id,
            "items_sha256": sha256_file(items_path),
            "oracle_manifest_sha256": sha256_file(oracle_manifest_path),
        }
    )
    return bound


def resolve_set_mode(args: argparse.Namespace) -> tuple[Path, Path, Path, Any]:
    root = Path(args.root).resolve()
    raw_set_root = Path(args.set_root)
    set_root = within_root(root, raw_set_root if raw_set_root.is_absolute() else root / raw_set_root)
    if set_root is None:
        raise ContractError("set root escapes the declared root, including through a symlink")
    manifest_path = set_root / "validation_set_manifest.json"
    manifest, errors = read_json(manifest_path)
    if errors:
        raise ContractError(errors[0])
    items_path = resolve_root_file(root, manifest.get("items_path"), "items_path")
    oracle_path = resolve_root_file(root, manifest.get("oracle_manifest_path"), "oracle_manifest_path")
    output_path = resolve_root_path(root, manifest.get("oracle_results_path"), "oracle_results_path")
    return items_path, oracle_path, output_path, manifest.get("validation_set_id")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic item oracles and optionally persist a source-bound oracle-results artifact.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--set-root", help="Validation-set directory. Uses manifest-bound items, oracle manifest, and oracle-results paths.")
    parser.add_argument("--items")
    parser.add_argument("--oracle-manifest")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.set_root:
            if args.items or args.oracle_manifest or args.output:
                raise ContractError("--set-root cannot be combined with --items, --oracle-manifest, or --output")
            items_path, oracle_path, output_path, validation_set_id = resolve_set_mode(args)
        else:
            if not args.items or not args.oracle_manifest:
                raise ContractError("direct mode requires --items and --oracle-manifest")
            items_path = Path(args.items).resolve()
            oracle_path = Path(args.oracle_manifest).resolve()
            output_path = Path(args.output).resolve() if args.output else None
            preview, preview_errors = read_json(oracle_path)
            validation_set_id = preview.get("validation_set_id") if not preview_errors else None
        items, item_errors = read_jsonl(items_path)
        manifest, manifest_errors = read_json(oracle_path)
        result = bind_result(
            analyze(items, manifest, item_errors + manifest_errors),
            validation_set_id=validation_set_id or manifest.get("validation_set_id"),
            items_path=items_path,
            oracle_manifest_path=oracle_path,
        )
        if output_path is not None:
            atomic_write_json(output_path, result, root=Path(args.root).resolve() if args.set_root else None)
    except (ContractError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        json.dump({"status": "failed", "execution_status": "failed", "error": str(exc)}, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if result["status"] == "not_evaluated":
        return 3
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
