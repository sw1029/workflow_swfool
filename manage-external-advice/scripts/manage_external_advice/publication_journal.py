"""Immutable journal records for advice retirement publication."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import sha256_text
from .storage import advice_root


SCHEMA_VERSION = 1
JOURNAL_KIND = "mark_applied_publication"


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def digest(value: Any) -> str:
    return sha256_text(canonical(value))


def sealed(record_kind: str, body: dict[str, Any]) -> dict[str, Any]:
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_kind": record_kind,
        **body,
    }
    record["record_digest"] = digest(record)
    return record


def sealed_bytes(record: dict[str, Any]) -> bytes:
    return (canonical(record) + "\n").encode("utf-8")


def validate_sealed(record: Any, expected_kind: str, path: Path) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise SystemExit(f"Invalid advice publication journal object: {path}")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(f"Unsupported advice publication journal schema: {path}")
    if record.get("record_kind") != expected_kind:
        raise SystemExit(f"Unexpected advice publication journal kind: {path}")
    claimed = record.get("record_digest")
    basis = {key: value for key, value in record.items() if key != "record_digest"}
    if claimed != digest(basis):
        raise SystemExit(f"Advice publication journal digest mismatch: {path}")
    return record


def read_sealed(path: Path, expected_kind: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"Unsafe advice publication journal path: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid advice publication journal {path}: {exc}") from exc
    return validate_sealed(value, expected_kind, path)


def journal_root(root: Path) -> Path:
    directory = advice_root(root) / "journal" / "mark_applied"
    try:
        directory.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit("Advice publication journal escapes the workspace.") from exc
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise SystemExit("Advice publication journal must be a regular directory.")
    return directory


def journal_path(root: Path, operation_digest: str, suffix: str) -> Path:
    return journal_root(root) / f"{operation_digest}.{suffix}.json"


def validate_prepare(record: dict[str, Any], path: Path) -> dict[str, Any]:
    validate_sealed(record, "prepare", path)
    operation_basis = record.get("operation_basis")
    if not isinstance(operation_basis, dict):
        raise SystemExit(f"Advice prepare journal lacks operation basis: {path}")
    if record.get("operation_digest") != digest(operation_basis):
        raise SystemExit(f"Advice prepare operation digest mismatch: {path}")
    if record.get("request_digest") != digest(record.get("request")):
        raise SystemExit(f"Advice prepare request digest mismatch: {path}")
    if path.name != f"{record['operation_digest']}.prepare.json":
        raise SystemExit(
            f"Advice prepare filename does not match operation digest: {path}"
        )
    return record


def matching_prepare(
    root: Path, advice_id: str, request_digest: str
) -> dict[str, Any] | None:
    directory = journal_root(root)
    if not directory.is_dir():
        return None
    matches: list[dict[str, Any]] = []
    same_advice: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.prepare.json")):
        record = validate_prepare(read_sealed(path, "prepare"), path)
        request = record.get("request")
        if isinstance(request, dict) and request.get("advice_id") == advice_id:
            same_advice.append(record)
            if record.get("request_digest") == request_digest:
                matches.append(record)
    if len(matches) > 1:
        raise SystemExit("Multiple prepare journals match one mark-applied request.")
    if not matches and same_advice:
        raise SystemExit(
            "A prepared mark-applied operation exists with a different request; retry its exact evidence and dispositions."
        )
    return matches[0] if matches else None


__all__ = (
    "JOURNAL_KIND",
    "canonical",
    "digest",
    "journal_path",
    "matching_prepare",
    "read_sealed",
    "sealed",
    "sealed_bytes",
)
