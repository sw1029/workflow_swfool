#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def resolve(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def rel(root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def build(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    manifest_path = resolve(root, args.manifest) or (resolve(root, args.set_root) / "validation_set_manifest.json")  # type: ignore[operator]
    manifest = read_json(manifest_path)
    file_fields = {
        "manifest": manifest_path,
        "items": resolve(root, manifest.get("items_path")),
        "labels": resolve(root, manifest.get("labels_path")),
        "oracle_manifest": resolve(root, manifest.get("oracle_manifest_path")),
        "split_manifest": resolve(root, manifest.get("split_manifest_path")),
        "leakage_report": resolve(root, manifest.get("leakage_report_path")),
    }
    file_hashes = {name: {"path": rel(root, path), "sha256": sha256_file(path) if path else None} for name, path in file_fields.items()}
    root_doc = {
        "created_at": now_iso(),
        "validation_set_id": manifest.get("validation_set_id"),
        "task_id": manifest.get("task_id"),
        "cycle_id": manifest.get("cycle_id"),
        "quality_tier": manifest.get("quality_tier"),
        "not_gold": manifest.get("not_gold", True),
        "validation_set_status": manifest.get("validation_set_status"),
        "file_hashes": file_hashes,
        "root_type": "validation_set_root",
    }
    output = resolve(root, args.output) or (manifest_path.parent / "validation_set_root.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(root_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    root_doc["path"] = rel(root, output)
    return root_doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze a validation-set root by hashing its manifest-bound files.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--set-root")
    parser.add_argument("--manifest")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if not args.manifest and not args.set_root:
        parser.error("one of --manifest or --set-root is required")
    result = build(args)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
