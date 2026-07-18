"""Validate evidence-bound clause dispositions before container retirement."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import sha256_file
from .packet_contract import clause_id_sets


ALLOWED_DISPOSITIONS = {"incorporated", "retired", "residual"}


def _full_sha256(value: Any) -> bool:
    normalized = str(value or "").strip().lower().removeprefix("sha256:")
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _load_json(root: Path, value: str) -> Any:
    stripped = value.lstrip()
    if stripped.startswith(("[", "{")):
        return json.loads(value)
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    if candidate.is_file():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return json.loads(value)


def _workspace_evidence(root: Path, ref: Any, digest: Any) -> tuple[str, str]:
    if not isinstance(ref, str) or not ref.strip() or Path(ref).is_absolute():
        raise SystemExit(
            "Every directive disposition evidence_ref must be a workspace-relative file."
        )
    if not _full_sha256(digest):
        raise SystemExit("Every directive disposition requires a full evidence_sha256.")
    candidate = root / ref
    if candidate.is_symlink() or not candidate.is_file():
        raise SystemExit(f"Directive disposition evidence is not a regular file: {ref}")
    resolved_root = root.resolve()
    try:
        candidate.resolve().relative_to(resolved_root)
    except ValueError as exc:
        raise SystemExit(
            f"Directive disposition evidence escapes workspace: {ref}"
        ) from exc
    observed = sha256_file(candidate)
    normalized = str(digest).strip().lower().removeprefix("sha256:")
    if observed != normalized:
        raise SystemExit(f"Directive disposition evidence digest mismatch: {ref}")
    return ref, normalized


def validate_directive_dispositions(
    root: Path,
    item: dict[str, Any],
    raw_json_or_path: str,
) -> list[dict[str, str]]:
    try:
        raw = _load_json(root, raw_json_or_path)
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Invalid directive dispositions JSON: {exc}") from exc
    if isinstance(raw, dict):
        raw = raw.get("rows")
    if not isinstance(raw, list) or not all(isinstance(row, dict) for row in raw):
        raise SystemExit(
            "Directive dispositions must be a JSON row list or {rows:[...]} object."
        )
    _, actionable_ids = clause_id_sets(item)
    expected_ids = set(actionable_ids)
    observed_ids = [str(row.get("directive_id") or "") for row in raw]
    if len(observed_ids) != len(set(observed_ids)):
        raise SystemExit(
            "Directive dispositions contain duplicate directive_id values."
        )
    if set(observed_ids) != expected_ids:
        missing = sorted(expected_ids - set(observed_ids))
        extra = sorted(set(observed_ids) - expected_ids)
        raise SystemExit(
            f"Directive dispositions must cover every actionable directive; missing={missing}, extra={extra}"
        )
    validated: list[dict[str, str]] = []
    for row in raw:
        state = str(row.get("disposition") or row.get("state") or "").strip().lower()
        if state not in ALLOWED_DISPOSITIONS:
            raise SystemExit(
                f"Invalid directive disposition for {row.get('directive_id')}: {state}"
            )
        ref, digest = _workspace_evidence(
            root, row.get("evidence_ref"), row.get("evidence_sha256")
        )
        validated.append(
            {
                "directive_id": str(row["directive_id"]),
                "disposition": state,
                "evidence_ref": ref,
                "evidence_sha256": digest,
            }
        )
    return validated


__all__ = ("ALLOWED_DISPOSITIONS", "validate_directive_dispositions")
