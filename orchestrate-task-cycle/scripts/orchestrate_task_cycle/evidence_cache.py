#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any


CACHE_FORMAT_VERSION = 1
SUPPORTED_CACHE_FORMAT_VERSIONS = {0, CACHE_FORMAT_VERSION}
SUCCESS_STATUSES = {"passed", "complete", "success", "ok"}
UNSAFE_STATUSES = {"failed", "partial", "running", "blocked", "skipped", "not_run"}
RESULT_STATUSES = SUCCESS_STATUSES | UNSAFE_STATUSES


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


def sha256_path(path: Path) -> tuple[str | None, str]:
    if path.is_file():
        return sha256_file(path), "file"
    if path.is_dir():
        digest = hashlib.sha256()
        digest.update(b"directory-v1\0")
        for child in sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix()):
            relative = child.relative_to(path).as_posix()
            if child.is_symlink():
                digest.update(f"L\0{relative}\0{os.readlink(child)}\n".encode("utf-8"))
            elif child.is_file():
                child_hash = sha256_file(child)
                if child_hash is None:
                    raise ValueError(f"cannot hash evidence file: {child}")
                digest.update(f"F\0{relative}\0{child_hash}\n".encode("utf-8"))
            elif child.is_dir():
                digest.update(f"D\0{relative}\n".encode("utf-8"))
        return digest.hexdigest(), "directory"
    return None, "missing"


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_workspace_path(root: Path, value: str, *, allow_absolute: bool = True) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        if not allow_absolute:
            raise ValueError(f"absolute path is not allowed here: {value}")
        return raw.resolve()
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"relative path escapes workspace root: {value}") from exc
    return candidate


def file_fingerprints(root: Path, values: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for value in sorted(set(values)):
        path = resolve_workspace_path(root, value)
        digest, kind = sha256_path(path)
        result.append({"path": rel_path(root, path), "exists": path.exists(), "kind": kind, "sha256": digest})
    return result


def env_fingerprints(values: list[str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for value in values:
        if "=" in value:
            name, raw = value.split("=", 1)
        else:
            name, raw = value, ""
        name = name.strip()
        if not name:
            raise ValueError("environment fingerprint names must be non-empty")
        result.append({"name": name, "value_sha256": sha256_bytes(raw.encode("utf-8"))})
    return sorted(result, key=lambda item: item["name"])


def load_extra(root: Path, value: str | None) -> Any:
    if not value:
        return None
    if value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else None
    stripped = value.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    path = resolve_workspace_path(root, value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def validate_fingerprint_details(details: dict[str, Any]) -> None:
    if not str(details.get("command") or "").strip():
        raise ValueError("evidence fingerprints require a non-empty command")
    file_groups = (
        "inputs",
        "schemas",
        "dependencies",
        "validation_set_roots",
        "oracle_manifests",
        "split_manifests",
        "leakage_reports",
        "source_artifacts",
    )
    file_entries = [entry for group in file_groups for entry in details.get(group, [])]
    invalid_paths = [entry.get("path") for entry in file_entries if not entry.get("exists") or not entry.get("sha256")]
    if invalid_paths:
        raise ValueError(f"fingerprint paths must exist and be hashable: {invalid_paths}")
    context_present = bool(
        file_entries
        or details.get("schema_contract_versions")
        or details.get("environment")
        or details.get("extra") not in (None, "", [], {})
    )
    if not context_present:
        raise ValueError(
            "evidence fingerprints require at least one hashed input/schema/dependency/artifact, "
            "schema contract version, environment value, or non-empty extra context"
        )


def build_fingerprint(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    schema_contract_versions = [str(value).strip() for value in (args.schema_contract_version or [])]
    if any(not value for value in schema_contract_versions):
        raise ValueError("schema contract version fingerprints must be non-empty")
    details = {
        "command": str(args.command or "").strip(),
        "validation_profile": args.profile or "current_only",
        "inputs": file_fingerprints(root, args.input or []),
        "schemas": file_fingerprints(root, args.schema or []),
        "dependencies": file_fingerprints(root, args.dependency or []),
        "validation_set_roots": file_fingerprints(root, args.validation_set_root or []),
        "oracle_manifests": file_fingerprints(root, args.oracle_manifest or []),
        "split_manifests": file_fingerprints(root, args.split_manifest or []),
        "leakage_reports": file_fingerprints(root, args.leakage_report or []),
        "source_artifacts": file_fingerprints(root, args.source_artifact or []),
        "schema_contract_versions": sorted(set(schema_contract_versions)),
        "environment": env_fingerprints(args.env or []),
        "extra": load_extra(root, args.extra_json),
    }
    validate_fingerprint_details(details)
    canonical = json.dumps(
        {"format_version": CACHE_FORMAT_VERSION, "details": details},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "format_version": CACHE_FORMAT_VERSION,
        "fingerprint": sha256_bytes(canonical.encode("utf-8")),
        "details": details,
    }


def cache_path(root: Path, path_value: str | None) -> Path:
    if not path_value:
        return root / ".task" / "evidence_cache" / "index.jsonl"
    return resolve_workspace_path(root, path_value)


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def cache_lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.lock")


@contextmanager
def cache_lock(path: Path, *, exclusive: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(cache_lock_path(path), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a+b", closefd=True) as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def durable_append_json(path: Path, value: dict[str, Any]) -> None:
    existed = path.exists()
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    with path.open("ab") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    if not existed:
        fsync_directory(path.parent)


def validate_stored_record(value: Any, line_no: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"evidence cache line {line_no} must contain a JSON object")
    version = value.get("format_version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version not in SUPPORTED_CACHE_FORMAT_VERSIONS:
        raise ValueError(f"unsupported evidence cache format_version {version!r} on line {line_no}")
    if not str(value.get("fingerprint") or "").strip():
        raise ValueError(f"evidence cache line {line_no} lacks a fingerprint")
    if not isinstance(value.get("details"), dict):
        raise ValueError(f"evidence cache line {line_no} lacks fingerprint details")
    if not str(value.get("result_status") or "").strip():
        raise ValueError(f"evidence cache line {line_no} lacks result_status")
    return value


def _read_record_lines(handle: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_record_ids: set[str] = set()
    for line_no, line in enumerate(handle, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"malformed evidence cache JSON on line {line_no}: {exc}"
            ) from exc
        record = validate_stored_record(value, line_no)
        record_id = record.get("record_id")
        if record_id:
            record_id = str(record_id)
            if record_id in seen_record_ids:
                raise ValueError(
                    f"duplicate evidence cache record_id `{record_id}` "
                    f"on line {line_no}"
                )
            seen_record_ids.add(record_id)
        records.append(record)
    return records


def read_records_unlocked(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return _read_record_lines(handle)


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            return _read_record_lines(handle)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def verify_record_evidence(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    refs = record.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        return {"valid": False, "reason": "evidence_hashes_missing", "invalid_paths": record.get("evidence_paths") or []}
    invalid: list[str] = []
    for ref in refs:
        if not isinstance(ref, dict) or not ref.get("path") or not ref.get("sha256"):
            invalid.append(str(ref.get("path") if isinstance(ref, dict) else ref))
            continue
        try:
            path = resolve_workspace_path(root, str(ref["path"]))
            digest, kind = sha256_path(path)
        except (OSError, ValueError):
            invalid.append(str(ref["path"]))
            continue
        if digest != ref.get("sha256") or kind != ref.get("kind"):
            invalid.append(str(ref["path"]))
    return {
        "valid": not invalid,
        "reason": "verified" if not invalid else "stored_evidence_missing_or_changed",
        "invalid_paths": invalid,
    }


def classify_candidate(
    fingerprint: dict[str, Any],
    records: list[dict[str, Any]],
    fresh_required: bool,
    root: Path | None = None,
) -> dict[str, Any]:
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
        evidence = verify_record_evidence(root, latest) if root is not None else {"valid": False, "reason": "workspace_root_missing", "invalid_paths": []}
        if not evidence["valid"]:
            return {"classification": "unsafe_to_reuse", "reason": evidence["reason"], "candidate": latest, "evidence_verification": evidence}
        if status in SUCCESS_STATUSES:
            return {"classification": "reuse", "reason": "exact_fingerprint_match", "candidate": latest, "evidence_verification": evidence}
        return {"classification": "unsafe_to_reuse", "reason": "prior_matching_evidence_not_successful", "candidate": latest}
    if comparable:
        latest = comparable[-1]
        status = str(latest.get("result_status") or "").lower()
        evidence = verify_record_evidence(root, latest) if root is not None else {"valid": False, "reason": "workspace_root_missing", "invalid_paths": []}
        if not evidence["valid"]:
            return {"classification": "unsafe_to_reuse", "reason": evidence["reason"], "candidate": latest, "evidence_verification": evidence}
        if status in UNSAFE_STATUSES or status not in RESULT_STATUSES:
            return {"classification": "unsafe_to_reuse", "reason": "comparable_prior_evidence_not_successful", "candidate": latest}
        return {"classification": "stale", "reason": "same_command_profile_but_fingerprint_changed", "candidate": latest}
    return {"classification": "fresh_required", "reason": "no_comparable_evidence", "candidate": None}


def store_record(path: Path, fingerprint: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    fingerprint_version = fingerprint.get("format_version")
    if isinstance(fingerprint_version, bool) or fingerprint_version != CACHE_FORMAT_VERSION:
        raise ValueError("stored fingerprints must use the current cache format_version")
    if not str(fingerprint.get("fingerprint") or "") or not isinstance(fingerprint.get("details"), dict):
        raise ValueError("stored fingerprint payload is incomplete")
    status = str(args.result_status or "").strip().lower()
    if status not in RESULT_STATUSES:
        raise ValueError(f"unsupported result_status: {args.result_status}")
    evidence_refs = file_fingerprints(root, args.evidence_path or [])
    if not evidence_refs:
        raise ValueError("storing evidence requires at least one --evidence-path")
    invalid_paths = [ref["path"] for ref in evidence_refs if not ref.get("exists") or not ref.get("sha256")]
    if invalid_paths:
        raise ValueError(f"stored evidence paths must exist and be hashable: {invalid_paths}")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "format_version": CACHE_FORMAT_VERSION,
        "record_id": f"evidence-{uuid.uuid4().hex}",
        "created_at": now_iso(),
        "fingerprint": fingerprint["fingerprint"],
        "details": fingerprint["details"],
        "result_status": status,
        "evidence_paths": [str(ref["path"]) for ref in evidence_refs],
        "evidence_refs": evidence_refs,
        "task_id": args.task_id,
        "cycle_id": args.cycle_id,
    }
    with cache_lock(path, exclusive=True):
        read_records_unlocked(path)
        durable_append_json(path, record)
    return record


def add_fingerprint_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".")
    parser.add_argument("--command", help="Exact command or canonical argv serialization; required for a usable fingerprint.")
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
    store.add_argument("--result-status", required=True, choices=sorted(RESULT_STATUSES))
    store.add_argument("--evidence-path", action="append", default=[])
    store.add_argument("--task-id")
    store.add_argument("--cycle-id")

    args = parser.parse_args(argv)
    fingerprint = build_fingerprint(args)
    if args.command_name == "fingerprint":
        output = fingerprint
    elif args.command_name == "check":
        root = Path(args.root).resolve()
        path = cache_path(root, args.cache)
        output = {"cache_path": str(path), **fingerprint, **classify_candidate(fingerprint, read_records(path), args.fresh_required, root)}
    else:
        path = cache_path(Path(args.root).resolve(), args.cache)
        output = {"cache_path": str(path), "record": store_record(path, fingerprint, args)}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
