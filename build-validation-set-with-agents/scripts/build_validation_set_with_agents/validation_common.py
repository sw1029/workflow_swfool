"""Shared validation-set vocabulary and bounded readers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ALLOWED_SOURCE_CLASSES = {
    "test_fixture",
    "synthetic_fixture",
    "sampled_real_metadata",
    "sampled_real_positive_evidence",
    "real_reviewed_work",
    "local_dataset_candidate",
    "external_metadata",
    "generated_candidate",
}
QUALITY_TIERS = {"candidate", "silver", "human_review_required", "gold"}
VALIDATION_SET_STATUSES = {"complete", "partial", "blocked", "not_applicable", "candidate_only"}
CONSUMABLE_STATUSES = {"complete"}
LABEL_TYPES = {"deterministic", "executable", "agent_consensus", "human_reviewed", "reference"}
LABEL_STATUSES = {"candidate", "accepted", "rejected", "needs_human_review", "blocked"}
ORACLE_TYPES = {"deterministic", "executable", "span_hash", "reference", "agent_consensus", "human_reviewed"}
ORACLE_TARGETS = {"item", "label", "set", "output", "root"}
SEALED_HOLDOUT_STATUSES = {"true_sealed", "quasi_sealed", "not_sealed", "not_applicable"}
FORBIDDEN_RAW_FIELDS = {"raw_body", "provider_body", "full_text", "source_text", "document_body"}
STRICT_BOOLEAN_FIELDS = {
    "not_gold",
    "fully_deterministic_authoritative_oracle",
    "premise_satisfied",
    "expectation_lineage_stale",
    "gating_axis_expected_pass",
    "report_key_divergence_expected",
    "acceptance_inversion_candidate",
    "sealed_holdout_labels_exposed",
    "authoritative",
}


def add(findings: list[dict[str, Any]], severity: str, code: str, message: str, evidence: Any = None) -> None:
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if evidence is not None:
        item["evidence"] = evidence
    findings.append(item)


def nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def is_json_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def is_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalized_field_name(value: str) -> str:
    with_word_boundaries = re.sub(r"(?<!^)(?=[A-Z])", "_", value)
    return with_word_boundaries.casefold().replace("-", "_")


def walk_forbidden(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child = f"{path}.{key_text}"
            if normalized_field_name(key_text) in FORBIDDEN_RAW_FIELDS:
                found.append(child)
            found.extend(walk_forbidden(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(walk_forbidden(item, f"{path}[{index}]"))
    return found


def validate_boolean_fields(value: Any, findings: list[dict[str, Any]], path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key) in STRICT_BOOLEAN_FIELDS and type(item) is not bool:
                add(
                    findings,
                    "block",
                    "invalid_boolean_type",
                    f"`{key}` must be a JSON boolean, not a truthy/falsy substitute.",
                    {"path": child, "value": item},
                )
            validate_boolean_fields(item, findings, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_boolean_fields(item, findings, f"{path}[{index}]")


def read_json(path: Path, findings: list[dict[str, Any]], artifact: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        add(findings, "block", "invalid_json_artifact", f"`{artifact}` is not valid UTF-8 JSON.", {"path": str(path), "error": str(exc)})
        return {}
    if not isinstance(value, dict):
        add(findings, "block", "invalid_json_artifact_type", f"`{artifact}` must contain a JSON object.", {"path": str(path)})
        return {}
    return value


def read_jsonl(path: Path, findings: list[dict[str, Any]], artifact: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    add(findings, "block", "invalid_jsonl_record", f"`{artifact}` contains invalid JSON.", {"path": str(path), "line": line_number, "error": str(exc)})
                    continue
                if not isinstance(value, dict):
                    add(findings, "block", "invalid_jsonl_record_type", f"`{artifact}` records must be JSON objects.", {"path": str(path), "line": line_number})
                    continue
                records.append(value)
    except (OSError, UnicodeError) as exc:
        add(findings, "block", "unreadable_jsonl_artifact", f"`{artifact}` could not be read as UTF-8 JSONL.", {"path": str(path), "error": str(exc)})
    return records


def within_root(root: Path, candidate: Path) -> Path | None:
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def resolve_manifest_path(
    root: Path,
    base: Path,
    value: Any,
    field: str,
    findings: list[dict[str, Any]],
) -> Path | None:
    if not is_string(value):
        return None
    raw = Path(value)
    candidates = [raw] if raw.is_absolute() else [root / raw, base / raw]
    selected: Path | None = None
    for candidate in candidates:
        bounded = within_root(root, candidate)
        if bounded is None:
            continue
        if bounded.is_file():
            selected = bounded
            break
        if selected is None:
            selected = bounded
    if selected is None:
        add(findings, "block", "manifest_path_escape", f"`{field}` escapes the declared root, including through a symlink.", {"path": value})
        return None
    return selected


def require_fields(record: dict[str, Any], fields: tuple[str, ...], findings: list[dict[str, Any]], code: str, subject: str) -> None:
    for field in fields:
        if field not in record or not nonempty(record.get(field)):
            add(findings, "block", code, f"{subject} is missing `{field}`.", {"field": field})
