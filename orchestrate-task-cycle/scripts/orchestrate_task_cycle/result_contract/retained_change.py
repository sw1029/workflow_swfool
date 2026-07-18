"""Classify retained changes from actual paths and content digests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from .accessors import deep_get


@dataclass(frozen=True, slots=True)
class RetainedChangeAssessment:
    evaluated: bool
    changed_files: tuple[str, ...]
    producer_body_changed: bool
    producer_source_changed: bool
    semantic_logic_changed: bool
    tests_only_changed: bool
    schema_or_verifier_only_changed: bool
    lifecycle_only_changed: bool
    progress_cap: str
    invalid_evidence_fields: tuple[str, ...]


def _mapping(result: dict[str, Any], *paths: str) -> dict[str, Any]:
    for path in paths:
        value = deep_get(result, path)
        if isinstance(value, dict):
            return value
    return {}


def _full_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_sha256(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_file_change_receipt_sha256(row: dict[str, Any]) -> str:
    return _canonical_sha256(
        {
            "path": row.get("path"),
            "change_kind": row.get("change_kind"),
            "subject_id": row.get("subject_id"),
            "before_sha256": row.get("before_sha256"),
            "after_sha256": row.get("after_sha256"),
        }
    )


def canonical_role_change_receipt_sha256(role: str, row: dict[str, Any]) -> str:
    return _canonical_sha256(
        {
            "role": role,
            "subject_id": row.get("subject_id"),
            "before_sha256": row.get("before_sha256"),
            "after_sha256": row.get("after_sha256"),
        }
    )


def _digest_pair(
    evidence: dict[str, Any], role: str
) -> tuple[bool | None, tuple[str, ...]]:
    role_evidence = evidence.get(role)
    role_map = role_evidence if isinstance(role_evidence, dict) else {}
    before = role_map.get("before_sha256") or role_map.get("before_digest")
    after = role_map.get("after_sha256") or role_map.get("after_digest")
    subject_id = role_map.get("subject_id") or evidence.get(f"{role}_subject_id")
    before = before or evidence.get(f"{role}_before_sha256")
    after = after or evidence.get(f"{role}_after_sha256")
    declared = bool(role_map) or any(
        key in evidence for key in (f"{role}_before_sha256", f"{role}_after_sha256")
    )
    if not declared:
        return None, ()
    invalid = tuple(
        field
        for field, value in (
            (f"{role}.subject_id", subject_id),
            (f"{role}.before_sha256", before),
            (f"{role}.after_sha256", after),
        )
        if not (
            isinstance(value, str) and value.strip()
            if field.endswith("subject_id")
            else _full_sha256(value)
        )
    )
    if invalid:
        return None, invalid
    receipt_sha256 = role_map.get("receipt_sha256")
    if not _full_sha256(
        receipt_sha256
    ) or receipt_sha256 != canonical_role_change_receipt_sha256(role, role_map):
        return None, (f"{role}.receipt_sha256",)
    return before != after, ()


def _changed_file_values(
    result: dict[str, Any], evidence: dict[str, Any]
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    rows = evidence.get("file_changes")
    rows_declared = "file_changes" in evidence
    invalid: list[str] = []
    normalized_rows: list[str] = []
    if rows_declared:
        if not isinstance(rows, list):
            invalid.append("retained_change_evidence.file_changes")
        else:
            for index, row in enumerate(rows):
                prefix = f"retained_change_evidence.file_changes[{index}]"
                if not isinstance(row, dict):
                    invalid.append(prefix)
                    continue
                path_value = row.get("path")
                path = (
                    path_value.strip().replace("\\", "/")
                    if isinstance(path_value, str)
                    else ""
                )
                kind = str(row.get("change_kind") or "").strip().lower()
                subject_id = row.get("subject_id")
                before = row.get("before_sha256")
                after = row.get("after_sha256")
                valid_path = bool(
                    path
                    and not PurePosixPath(path).is_absolute()
                    and ".." not in PurePosixPath(path).parts
                )
                valid_digests = bool(
                    kind == "added"
                    and before is None
                    and _full_sha256(after)
                    or kind == "deleted"
                    and _full_sha256(before)
                    and after is None
                    or kind == "modified"
                    and _full_sha256(before)
                    and _full_sha256(after)
                    and before != after
                )
                receipt = row.get("receipt_sha256")
                if not (
                    valid_path
                    and isinstance(subject_id, str)
                    and subject_id.strip()
                    and valid_digests
                    and _full_sha256(receipt)
                    and receipt == canonical_file_change_receipt_sha256(row)
                ):
                    invalid.append(prefix)
                    continue
                normalized_rows.append(path)
            if len(normalized_rows) != len(set(normalized_rows)):
                invalid.append("retained_change_evidence.file_changes.path_duplicate")
    candidates = (
        "retained_change_evidence.actual_changed_files",
        "scoped_progress.retained_change_evidence.actual_changed_files",
        "actual_changed_files",
        "result.actual_changed_files",
        "retained_change_evidence.changed_files",
        "scoped_progress.retained_change_evidence.changed_files",
        "changed_files",
        "result.changed_files",
    )
    claimed_files: tuple[str, ...] | None = None
    for path in candidates:
        parent_path, _, field = path.rpartition(".")
        parent = deep_get(result, parent_path) if parent_path else result
        if not isinstance(parent, dict) or field not in parent:
            continue
        value = parent.get(field)
        if not isinstance(value, list):
            invalid.append(path)
            break
        claimed_files = tuple(
            sorted(
                {
                    item.strip().replace("\\", "/")
                    for item in value
                    if isinstance(item, str) and item.strip()
                }
            )
        )
        break
    retained_files = tuple(sorted(normalized_rows))
    if claimed_files is not None and claimed_files != retained_files:
        invalid.append("retained_change_evidence.file_changes.binding")
    if claimed_files is not None and not rows_declared:
        invalid.append("retained_change_evidence.file_changes")
    return (
        bool(rows_declared and isinstance(rows, list) and not invalid),
        retained_files,
        tuple(sorted(set(invalid))),
    )


def _path_role(path_text: str) -> str:
    path = PurePosixPath(path_text.lower())
    parts = set(path.parts)
    name = path.name
    suffix = path.suffix
    if parts & {".task", ".agent_goal", ".agent_log", ".agent_issue"}:
        return "lifecycle"
    if (
        parts & {"test", "tests", "spec", "specs", "__tests__", "fixtures"}
        or name.startswith("test_")
        or name.endswith(("_test.py", ".spec.js", ".spec.ts", ".test.js", ".test.ts"))
    ):
        return "test"
    if parts & {"verifier", "verifiers"} or "verifier" in name:
        return "verifier"
    if parts & {"schema", "schemas", "contract", "contracts"}:
        return "schema"
    if suffix in {".jsonschema", ".avsc", ".proto", ".xsd"}:
        return "schema"
    if suffix in {".md", ".rst", ".adoc"} or parts & {"docs", "references"}:
        return "governance"
    if suffix in {
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".rb",
        ".php",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".sh",
    }:
        return "source"
    return "other"


def _progress_cap(
    roles: set[str],
    *,
    producer_body_changed: bool,
    producer_source_changed: bool,
    semantic_logic_changed: bool,
) -> str:
    if semantic_logic_changed or producer_body_changed:
        return "semantic"
    if producer_source_changed:
        return "root_reduction"
    bounded_roles = {"test", "schema", "verifier", "lifecycle", "governance"}
    if roles and roles <= bounded_roles and "test" in roles:
        return "task_local"
    if roles and roles <= {"verifier"}:
        return "safety"
    if roles and roles <= {"schema", "verifier", "lifecycle", "governance"}:
        return "governance"
    return "none"


def classify_retained_change(result: dict[str, Any]) -> RetainedChangeAssessment:
    evidence = _mapping(
        result,
        "retained_change_evidence",
        "scoped_progress.retained_change_evidence",
        "result.retained_change_evidence",
    )
    files_verified, changed_files, changed_files_invalid = _changed_file_values(
        result, evidence
    )
    body_changed, body_invalid = _digest_pair(evidence, "producer_body")
    source_digest_changed, source_invalid = _digest_pair(evidence, "producer_source")
    semantic_changed, semantic_invalid = _digest_pair(evidence, "semantic_logic")
    roles = tuple(_path_role(path) for path in changed_files)
    evaluated = files_verified or any(
        value is not None
        for value in (body_changed, source_digest_changed, semantic_changed)
    )
    producer_body_changed = bool(body_changed)
    producer_source_changed = bool(source_digest_changed) or "source" in roles
    semantic_logic_changed = bool(semantic_changed)
    role_set = set(roles)
    return RetainedChangeAssessment(
        evaluated=evaluated,
        changed_files=changed_files,
        producer_body_changed=producer_body_changed,
        producer_source_changed=producer_source_changed,
        semantic_logic_changed=semantic_logic_changed,
        tests_only_changed=bool(roles) and role_set == {"test"},
        schema_or_verifier_only_changed=bool(roles)
        and role_set <= {"schema", "verifier"},
        lifecycle_only_changed=bool(roles) and role_set == {"lifecycle"},
        progress_cap=_progress_cap(
            role_set,
            producer_body_changed=producer_body_changed,
            producer_source_changed=producer_source_changed,
            semantic_logic_changed=semantic_logic_changed,
        ),
        invalid_evidence_fields=(
            *changed_files_invalid,
            *body_invalid,
            *source_invalid,
            *semantic_invalid,
        ),
    )


__all__ = (
    "RetainedChangeAssessment",
    "canonical_file_change_receipt_sha256",
    "canonical_role_change_receipt_sha256",
    "classify_retained_change",
)
