#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from freeze_validation_set_root import LEGACY_REQUIRED_HASH_FIELDS, REQUIRED_HASH_FIELDS, RootFreezeError, bound_path, payload_sha256, read_json_object, sha256_file
from validate_validation_set import validate as validate_set
from validation_set_contract import ROOT_SCHEMA_VERSION


SHA256 = re.compile(r"^[0-9a-f]{64}$")


def add(findings: list[dict[str, Any]], code: str, message: str, evidence: Any = None) -> None:
    finding: dict[str, Any] = {"severity": "block", "code": code, "message": message}
    if evidence is not None:
        finding["evidence"] = evidence
    findings.append(finding)


def verify(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    findings: list[dict[str, Any]] = []
    if not root.is_dir():
        return {"status": "block", "findings": [{"severity": "block", "code": "invalid_root", "message": f"Declared root is not a directory: {root}"}]}
    raw_root_file = Path(args.root_file) if args.root_file else Path(args.set_root) / "validation_set_root.json"
    try:
        root_file = bound_path(root, raw_root_file if raw_root_file.is_absolute() else root / raw_root_file, "root_file")
        root_doc = read_json_object(root_file, "validation-set root")
    except RootFreezeError as exc:
        return {"status": "block", "findings": [{"severity": "block", "code": "invalid_root_file", "message": str(exc)}]}

    if root_doc.get("root_type") != "validation_set_root":
        add(findings, "invalid_root_type", "Root document has an invalid `root_type`.")
    if not isinstance(root_doc.get("created_at"), str) or not root_doc["created_at"].strip():
        add(findings, "missing_root_created_at", "Root document requires a non-empty `created_at` value.")
    root_schema_version = root_doc.get("root_schema_version")
    if type(root_schema_version) is not int or root_schema_version not in {1, ROOT_SCHEMA_VERSION}:
        add(findings, "invalid_root_schema_version", "Root document must use supported integer schema version 1 or 2.")
    if not isinstance(root_doc.get("validation_set_id"), str) or not root_doc["validation_set_id"].strip():
        add(findings, "missing_validation_set_id", "Root document requires a validation-set ID.")
    if type(root_doc.get("not_gold")) is not bool:
        add(findings, "invalid_root_boolean", "Root `not_gold` must be a JSON boolean.")
    declared_root_hash = root_doc.get("root_sha256")
    if not isinstance(declared_root_hash, str) or not SHA256.fullmatch(declared_root_hash):
        add(findings, "invalid_root_sha256", "Root document requires a lowercase SHA-256 binding digest.")
    else:
        try:
            actual_root_hash = payload_sha256(root_doc)
        except (KeyError, TypeError, ValueError) as exc:
            add(findings, "invalid_root_payload", "Root binding payload is incomplete or malformed.", {"error": str(exc)})
        else:
            if declared_root_hash != actual_root_hash:
                add(findings, "root_sha256_mismatch", "Root document binding digest does not match its canonical payload.", {"declared": declared_root_hash, "actual": actual_root_hash})

    declared_path = root_doc.get("path")
    if not isinstance(declared_path, str) or not declared_path.strip():
        add(findings, "missing_root_path", "Root document requires its root-relative `path`.")
    else:
        try:
            if Path(declared_path).is_absolute() or ".." in Path(declared_path).parts:
                raise RootFreezeError(f"root path must be root-relative without parent traversal: {declared_path}")
            declared_root_file = bound_path(root, root / declared_path, "root path")
            if declared_root_file != root_file:
                add(findings, "root_path_mismatch", "Root document path does not identify the verified root file.", {"declared": declared_path})
        except RootFreezeError as exc:
            add(findings, "root_path_escape", str(exc))

    file_hashes = root_doc.get("file_hashes")
    manifest_path: Path | None = None
    if not isinstance(file_hashes, dict):
        add(findings, "invalid_file_hashes", "Root document must contain a `file_hashes` object.")
        file_hashes = {}
    required_hash_fields = REQUIRED_HASH_FIELDS if root_schema_version == ROOT_SCHEMA_VERSION else LEGACY_REQUIRED_HASH_FIELDS
    unexpected_hash_fields = sorted(set(file_hashes) - set(required_hash_fields))
    if unexpected_hash_fields:
        add(findings, "unexpected_file_hash", "Root document contains file hashes outside its schema binding set.", unexpected_hash_fields)
    for name in required_hash_fields:
        entry = file_hashes.get(name)
        if not isinstance(entry, dict):
            add(findings, "missing_file_hash", f"Root document is missing the `{name}` file hash.")
            continue
        path_value = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(path_value, str) or not path_value.strip():
            add(findings, "invalid_hashed_path", f"`{name}` has a missing/null path.")
            continue
        if Path(path_value).is_absolute() or ".." in Path(path_value).parts:
            add(findings, "invalid_hashed_path", f"`{name}` path must be root-relative without parent traversal.", {"path": path_value})
            continue
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            add(findings, "invalid_file_sha256", f"`{name}` has a missing/null or malformed SHA-256 digest.")
            continue
        try:
            path = bound_path(root, root / path_value, f"file_hashes.{name}.path")
            actual = sha256_file(path)
        except RootFreezeError as exc:
            add(findings, "hashed_file_unavailable", str(exc), {"name": name, "path": path_value})
            continue
        if name == "manifest":
            manifest_path = path
        if actual != digest:
            add(findings, "file_sha256_mismatch", f"`{name}` no longer matches the frozen digest.", {"path": path_value, "declared": digest, "actual": actual})

    validation: dict[str, Any] | None = None
    if manifest_path is not None:
        validation_args = argparse.Namespace(root=str(root), manifest=str(manifest_path), set_root=None, warn_only=False)
        validation = validate_set(validation_args)
        if validation.get("status") == "block":
            add(findings, "bound_validation_set_invalid", "The manifest-bound validation set no longer passes fail-closed validation.", [item.get("code") for item in validation.get("findings", []) if item.get("severity") == "block"])
        try:
            manifest = read_json_object(manifest_path, "manifest")
        except RootFreezeError as exc:
            add(findings, "invalid_bound_manifest", str(exc))
        else:
            for field in ("validation_set_id", "task_id", "cycle_id", "quality_tier", "not_gold", "validation_set_status"):
                if root_doc.get(field) != manifest.get(field):
                    add(findings, "root_manifest_metadata_mismatch", f"Root `{field}` does not match its bound manifest.", {"root": root_doc.get(field), "manifest": manifest.get(field)})

    if root_doc.get("validation_set_status") == "complete" and (validation is None or validation.get("readiness") != "consumable"):
        add(findings, "bound_set_not_consumable", "A complete frozen root must still validate as consumable.")

    blocked = bool(findings)
    return {
        "status": "block" if blocked else "verified",
        "readiness": "blocked" if blocked else validation.get("readiness") if validation else "blocked",
        "validation_status": "block" if blocked else validation.get("status") if validation else "block",
        "bound_validation_status": validation.get("status") if validation else "block",
        "root_file": str(root_file),
        "validation_set_id": root_doc.get("validation_set_id"),
        "validation_set_status": root_doc.get("validation_set_status"),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify every validation-set root binding and the current fail-closed contract.")
    parser.add_argument("--root", default=".")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--set-root")
    group.add_argument("--root-file")
    args = parser.parse_args(argv)
    result = verify(args)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
