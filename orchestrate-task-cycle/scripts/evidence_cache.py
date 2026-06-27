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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def file_fingerprints(root: Path, values: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for value in values:
        path = (root / value).resolve() if not Path(value).is_absolute() else Path(value)
        result.append({"path": rel_path(root, path), "exists": path.exists(), "sha256": sha256_file(path)})
    return result


def env_fingerprints(values: list[str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for value in values:
        if "=" in value:
            name, raw = value.split("=", 1)
        else:
            name, raw = value, ""
        result.append({"name": name, "value_sha256": sha256_bytes(raw.encode("utf-8"))})
    return sorted(result, key=lambda item: item["name"])


def load_extra(value: str | None) -> Any:
    if not value:
        return None
    if value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else None
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def build_fingerprint(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    details = {
        "command": args.command or "",
        "validation_profile": args.profile or "current_only",
        "inputs": file_fingerprints(root, args.input or []),
        "schemas": file_fingerprints(root, args.schema or []),
        "dependencies": file_fingerprints(root, args.dependency or []),
        "validation_set_roots": file_fingerprints(root, args.validation_set_root or []),
        "oracle_manifests": file_fingerprints(root, args.oracle_manifest or []),
        "split_manifests": file_fingerprints(root, args.split_manifest or []),
        "leakage_reports": file_fingerprints(root, args.leakage_report or []),
        "source_artifacts": file_fingerprints(root, args.source_artifact or []),
        "schema_contract_versions": args.schema_contract_version or [],
        "environment": env_fingerprints(args.env or []),
        "extra": load_extra(args.extra_json),
    }
    canonical = json.dumps(details, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"fingerprint": sha256_bytes(canonical.encode("utf-8")), "details": details}


def cache_path(root: Path, path_value: str | None) -> Path:
    return Path(path_value) if path_value else root / ".task" / "evidence_cache" / "index.jsonl"


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    return records


def classify_candidate(fingerprint: dict[str, Any], records: list[dict[str, Any]], fresh_required: bool) -> dict[str, Any]:
    exact = [record for record in records if record.get("fingerprint") == fingerprint["fingerprint"]]
    command = fingerprint["details"].get("command")
    profile = fingerprint["details"].get("validation_profile")
    comparable = [
        record
        for record in records
        if record.get("details", {}).get("command") == command and record.get("details", {}).get("validation_profile") == profile
    ]
    if fresh_required:
        return {"classification": "fresh_required", "reason": "caller_required_fresh_evidence", "candidate": exact[-1] if exact else None}
    if exact:
        latest = exact[-1]
        status = str(latest.get("result_status") or "").lower()
        if status in {"passed", "complete", "success", "ok"}:
            return {"classification": "reuse", "reason": "exact_fingerprint_match", "candidate": latest}
        return {"classification": "unsafe_to_reuse", "reason": "prior_matching_evidence_not_successful", "candidate": latest}
    if comparable:
        latest = comparable[-1]
        status = str(latest.get("result_status") or "").lower()
        if status in {"failed", "partial", "running", "blocked"}:
            return {"classification": "unsafe_to_reuse", "reason": "comparable_prior_evidence_not_successful", "candidate": latest}
        return {"classification": "stale", "reason": "same_command_profile_but_fingerprint_changed", "candidate": latest}
    return {"classification": "fresh_required", "reason": "no_comparable_evidence", "candidate": None}


def store_record(path: Path, fingerprint: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "created_at": now_iso(),
        "fingerprint": fingerprint["fingerprint"],
        "details": fingerprint["details"],
        "result_status": args.result_status,
        "evidence_paths": args.evidence_path or [],
        "task_id": args.task_id,
        "cycle_id": args.cycle_id,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def add_fingerprint_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".")
    parser.add_argument("--command")
    parser.add_argument("--profile", choices=("current_only", "affected_chain", "full_chain"), default="current_only")
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--schema", action="append", default=[])
    parser.add_argument("--dependency", action="append", default=[])
    parser.add_argument("--validation-set-root", action="append", default=[])
    parser.add_argument("--oracle-manifest", action="append", default=[])
    parser.add_argument("--split-manifest", action="append", default=[])
    parser.add_argument("--leakage-report", action="append", default=[])
    parser.add_argument("--source-artifact", action="append", default=[])
    parser.add_argument("--schema-contract-version", action="append", default=[])
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--extra-json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fingerprint and classify reusable cycle evidence.")
    sub = parser.add_subparsers(dest="command_name", required=True)

    fp = sub.add_parser("fingerprint", help="Build an evidence fingerprint.")
    add_fingerprint_args(fp)

    check = sub.add_parser("check", help="Check cache reuse classification.")
    add_fingerprint_args(check)
    check.add_argument("--cache")
    check.add_argument("--fresh-required", action="store_true")

    store = sub.add_parser("store", help="Store evidence result in cache.")
    add_fingerprint_args(store)
    store.add_argument("--cache")
    store.add_argument("--result-status", required=True)
    store.add_argument("--evidence-path", action="append", default=[])
    store.add_argument("--task-id")
    store.add_argument("--cycle-id")

    args = parser.parse_args(argv)
    fingerprint = build_fingerprint(args)
    if args.command_name == "fingerprint":
        output = fingerprint
    elif args.command_name == "check":
        path = cache_path(Path(args.root).resolve(), args.cache)
        output = {"cache_path": str(path), **fingerprint, **classify_candidate(fingerprint, read_records(path), args.fresh_required)}
    else:
        path = cache_path(Path(args.root).resolve(), args.cache)
        output = {"cache_path": str(path), "record": store_record(path, fingerprint, args)}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
