#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .validate_validation_set import validate as validate_set
from .validation_set_contract import MANIFEST_SCHEMA_VERSION, ROOT_SCHEMA_VERSION, atomic_write_json


LEGACY_REQUIRED_HASH_FIELDS = ("manifest", "items", "labels", "oracle_manifest", "split_manifest", "leakage_report")
REQUIRED_HASH_FIELDS = ("manifest", "items", "labels", "oracle_manifest", "oracle_results", "split_manifest", "leakage_report")


class RootFreezeError(ValueError):
    pass


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise RootFreezeError(f"required file is missing: {path}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RootFreezeError(f"required file cannot be hashed: {path}: {exc}") from exc
    return digest.hexdigest()


def read_json_object(path: Path, artifact: str) -> dict[str, Any]:
    if not path.is_file():
        raise RootFreezeError(f"{artifact} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RootFreezeError(f"{artifact} is not valid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RootFreezeError(f"{artifact} must contain a JSON object: {path}")
    return value


def bound_path(root: Path, candidate: Path, label: str) -> Path:
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RootFreezeError(f"{label} escapes the declared root, including through a symlink: {candidate}") from exc
    return resolved


def resolve_input(root: Path, base: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise RootFreezeError(f"{label} is missing or is not a non-empty path string")
    raw = Path(value)
    candidates = [raw] if raw.is_absolute() else [root / raw, base / raw]
    bounded: list[Path] = []
    for candidate in candidates:
        try:
            bounded.append(bound_path(root, candidate, label))
        except RootFreezeError:
            continue
    for candidate in bounded:
        if candidate.is_file():
            return candidate
    if not bounded:
        raise RootFreezeError(f"{label} escapes the declared root, including through a symlink: {value}")
    raise RootFreezeError(f"{label} does not resolve to a file: {value}")


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def canonical_root_payload(root_doc: dict[str, Any]) -> dict[str, Any]:
    # Bind the complete root document, including creation/path metadata and
    # any future versioned fields. Only the digest field itself is excluded.
    return {key: value for key, value in root_doc.items() if key != "root_sha256"}


def payload_sha256(root_doc: dict[str, Any]) -> str:
    encoded = json.dumps(canonical_root_payload(root_doc), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise RootFreezeError(f"declared root is not a directory: {root}")
    raw_manifest = Path(args.manifest) if args.manifest else Path(args.set_root) / "validation_set_manifest.json"
    manifest_path = bound_path(root, raw_manifest if raw_manifest.is_absolute() else root / raw_manifest, "manifest")
    manifest = read_json_object(manifest_path, "manifest")
    if manifest.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION or type(manifest.get("manifest_schema_version")) is not int:
        raise RootFreezeError("legacy/versionless validation sets are migration_required and cannot be frozen; rebuild/finalize schema version 2")

    validation_args = argparse.Namespace(root=str(root), manifest=str(manifest_path), set_root=None, warn_only=False)
    validation = validate_set(validation_args)
    if validation.get("status") == "block":
        codes = sorted({str(item.get("code")) for item in validation.get("findings", []) if item.get("severity") == "block"})
        raise RootFreezeError(f"validation set is invalid and cannot be frozen: {', '.join(codes)}")
    if manifest.get("validation_set_status") == "complete" and validation.get("readiness") != "consumable":
        raise RootFreezeError("complete validation set is not consumable and cannot be frozen")

    paths = {
        "manifest": manifest_path,
        "items": resolve_input(root, manifest_path.parent, manifest.get("items_path"), "items_path"),
        "labels": resolve_input(root, manifest_path.parent, manifest.get("labels_path"), "labels_path"),
        "oracle_manifest": resolve_input(root, manifest_path.parent, manifest.get("oracle_manifest_path"), "oracle_manifest_path"),
        "oracle_results": resolve_input(root, manifest_path.parent, manifest.get("oracle_results_path"), "oracle_results_path"),
        "split_manifest": resolve_input(root, manifest_path.parent, manifest.get("split_manifest_path"), "split_manifest_path"),
        "leakage_report": resolve_input(root, manifest_path.parent, manifest.get("leakage_report_path"), "leakage_report_path"),
    }
    file_hashes: dict[str, dict[str, str]] = {}
    for name in REQUIRED_HASH_FIELDS:
        path = paths[name]
        digest = sha256_file(path)
        if not digest:
            raise RootFreezeError(f"computed null/empty hash for {name}: {path}")
        file_hashes[name] = {"path": relative_path(root, path), "sha256": digest}

    raw_output = Path(args.output) if args.output else manifest_path.parent / "validation_set_root.json"
    output = bound_path(root, raw_output if raw_output.is_absolute() else root / raw_output, "output")
    if output in paths.values():
        raise RootFreezeError("output path must not overwrite a manifest-bound validation artifact")
    root_doc: dict[str, Any] = {
        "created_at": now_iso(),
        "root_schema_version": ROOT_SCHEMA_VERSION,
        "validation_set_id": manifest["validation_set_id"],
        "task_id": manifest.get("task_id"),
        "cycle_id": manifest.get("cycle_id"),
        "quality_tier": manifest["quality_tier"],
        "not_gold": manifest["not_gold"],
        "validation_set_status": manifest["validation_set_status"],
        "file_hashes": file_hashes,
        "root_type": "validation_set_root",
        "path": relative_path(root, output),
    }
    root_doc["root_sha256"] = payload_sha256(root_doc)
    atomic_write_json(output, root_doc, root=root)
    return root_doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze a validation-set root after fail-closed artifact validation.")
    parser.add_argument("--root", default=".")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--set-root")
    group.add_argument("--manifest")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        result = build(args)
    except (RootFreezeError, OSError) as exc:
        json.dump({"status": "block", "error": str(exc)}, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
