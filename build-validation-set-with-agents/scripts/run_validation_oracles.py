#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.is_file():
        return records
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
    return records


def get_value(record: dict[str, Any], field: str) -> Any:
    current: Any = record
    for key in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def run_oracle(record: dict[str, Any], oracle: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for field in oracle.get("required_fields") or []:
        value = get_value(record, str(field))
        if value in (None, "", [], {}):
            failures.append(f"missing_required_field:{field}")
    for field in oracle.get("forbidden_fields") or []:
        value = get_value(record, str(field))
        if value not in (None, "", [], {}):
            failures.append(f"forbidden_field_present:{field}")
    allowed_values = oracle.get("allowed_values") or {}
    if isinstance(allowed_values, dict):
        for field, allowed in allowed_values.items():
            value = get_value(record, str(field))
            if isinstance(allowed, list) and value not in allowed:
                failures.append(f"disallowed_value:{field}:{value}")
    return failures


def analyze(items: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    oracles = manifest.get("oracles") if isinstance(manifest.get("oracles"), list) else []
    results: list[dict[str, Any]] = []
    for item in items:
        item_id = item.get("item_id") or item.get("id") or "unknown"
        for oracle in oracles:
            if oracle.get("target", "item") != "item":
                continue
            failures = run_oracle(item, oracle)
            results.append(
                {
                    "item_id": item_id,
                    "oracle_id": oracle.get("oracle_id") or "unknown",
                    "status": "failed" if failures else "passed",
                    "failures": failures,
                }
            )
    failed = [item for item in results if item["status"] == "failed"]
    return {"status": "failed" if failed else "passed", "item_count": len(items), "oracle_count": len(oracles), "result_count": len(results), "failed_count": len(failed), "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run simple deterministic validation-set oracles over item records.")
    parser.add_argument("--items", required=True)
    parser.add_argument("--oracle-manifest", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = analyze(read_jsonl(Path(args.items)), read_json(Path(args.oracle_manifest)))
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
