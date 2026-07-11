#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from validate_validation_set import validate as validate_set
from validation_set_contract import (
    ARTIFACT_FIELDS,
    MANIFEST_SCHEMA_VERSION,
    ContractError,
    atomic_write_json,
    build_finalization_record,
    resolve_root_file,
    within_root,
)


class FinalizationError(ContractError):
    pass


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FinalizationError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizationError(f"{label} is not valid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FinalizationError(f"{label} must contain a JSON object: {path}")
    return value


def read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.is_file():
        raise FinalizationError(f"{label} is missing: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise FinalizationError(f"{label} record {line_number} is not an object")
                records.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizationError(f"{label} is not valid UTF-8 JSONL: {path}: {exc}") from exc
    return records


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise FinalizationError(f"declared root is not a directory: {root}")
    raw_manifest = Path(args.manifest) if args.manifest else Path(args.set_root) / "validation_set_manifest.json"
    manifest_path = within_root(root, raw_manifest if raw_manifest.is_absolute() else root / raw_manifest)
    if manifest_path is None or not manifest_path.is_file():
        raise FinalizationError("manifest is missing or escapes the declared root, including through a symlink")
    manifest = read_json_object(manifest_path, "manifest")
    if manifest.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION or type(manifest.get("manifest_schema_version")) is not int:
        raise FinalizationError("only schema-v2 manifests can be finalized; rebuild legacy/versionless candidates")
    if manifest.get("validation_set_status") in {"blocked", "not_applicable"}:
        raise FinalizationError(f"validation-set status cannot be finalized: {manifest.get('validation_set_status')}")

    artifact_paths = {
        name: resolve_root_file(root, manifest.get(field), field)
        for name, field in ARTIFACT_FIELDS.items()
    }
    items = read_jsonl(artifact_paths["items"], "items")
    labels = read_jsonl(artifact_paths["labels"], "labels")
    oracle_manifest = read_json_object(artifact_paths["oracle_manifest"], "oracle manifest")
    oracle_results = read_json_object(artifact_paths["oracle_results"], "oracle results")

    proposed = dict(manifest)
    proposed["validation_set_status"] = "complete"
    proposed["item_count"] = len(items)
    proposed["label_count"] = len(labels)
    oracles = oracle_manifest.get("oracles")
    proposed["oracle_count"] = len(oracles) if isinstance(oracles, list) else 0
    proposed["source_class_distribution"] = dict(sorted(Counter(str(item.get("source_class")) for item in items).items()))
    flags = [
        value
        for value in proposed.get("no_overclaim_flags", [])
        if isinstance(value, str) and value != "candidate_only" and not (value == "not_gold" and proposed.get("not_gold") is False)
    ]
    if proposed.get("not_gold") is True and "not_gold" not in flags:
        flags.append("not_gold")
    proposed["no_overclaim_flags"] = sorted(set(flags))
    proposed["finalization_record"] = build_finalization_record(proposed, artifact_paths, oracle_results)

    validation_candidate = manifest_path.with_name(f".{manifest_path.name}.finalize-{os.getpid()}")
    try:
        atomic_write_json(validation_candidate, proposed, root=root)
        validation_args = argparse.Namespace(root=str(root), manifest=str(validation_candidate), set_root=None, warn_only=False)
        validation = validate_set(validation_args)
        if validation.get("status") != "ok" or validation.get("readiness") != "consumable":
            codes = sorted({str(item.get("code")) for item in validation.get("findings", []) if item.get("severity") in {"block", "warn"}})
            raise FinalizationError(f"candidate cannot be finalized: {', '.join(codes)}")
        os.replace(validation_candidate, manifest_path)
        directory_fd = os.open(manifest_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if validation_candidate.exists():
            validation_candidate.unlink()

    return {
        "status": "complete",
        "readiness": "consumable",
        "validation_set_id": proposed.get("validation_set_id"),
        "manifest_path": manifest_path.relative_to(root).as_posix(),
        "finalization_sha256": proposed["finalization_record"]["finalization_sha256"],
        "item_count": proposed["item_count"],
        "label_count": proposed["label_count"],
        "oracle_count": proposed["oracle_count"],
        "oracle_result_count": oracle_results.get("result_count"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atomically promote a schema-v2 candidate after source, leakage, split, oracle-result, and finalization validation.")
    parser.add_argument("--root", default=".")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--set-root")
    group.add_argument("--manifest")
    args = parser.parse_args(argv)
    try:
        result = finalize(args)
    except (FinalizationError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        json.dump({"status": "block", "error": str(exc)}, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
