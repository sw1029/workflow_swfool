"""Closed data contracts for selection authority re-entry."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any

from .selection_decision_store import (
    SHA256,
    canonical_bytes,
    canonical_sha256,
    closed_object,
    normalize_binding,
)


CYCLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
CANDIDATE_ID = re.compile(r"candidate-[A-Za-z0-9][A-Za-z0-9._-]{0,117}")
TASK_ID = re.compile(r"task-[A-Za-z0-9][A-Za-z0-9._-]{0,122}")
OPERATION_KEYS = {
    "skill_id",
    "skill_version",
    "operation_id",
    "operation_version",
}
SUBJECT_KEYS = {"kind", "ref", "digest", "revision"}
SUBJECT_CANDIDATE_IDENTITY_KEYS = (
    "candidate_id",
    "exact_subject_work_id",
    "task_kind",
    "expected_blocker_transition",
)
DECISION_ENTRY_KEYS = {
    "decision",
    "decision_id",
    "request_sha256",
    "request_semantic_sha256",
    "operation",
}
SOURCE_AUTHORITY_REQUEST_KEYS = {
    "decision",
    "request_sha256",
    "request_semantic_sha256",
}
REQUEST_ALLOCATION_IDENTITY_KEYS = frozenset(
    {"request_id", "attempt_id", "idempotency_key"}
)
RESOLUTION_KEYS = {
    "schema_version",
    "artifact_kind",
    "resolution_id",
    "selection_trigger",
    "source_selection_synthesis",
    "source_cycle_id",
    "source_derive",
    "source_outcome",
    "authority_reentry_at",
    "candidate",
    "candidate_sha256",
    "authority_subject",
    "source_authority_request",
    "authority_decisions",
    "source_approval",
    "root_materialization_ref",
    "authorized_operations",
    "selected_task_id",
    "task_source",
    "not_goal_truth",
    "not_authority",
    "not_validation_evidence",
    "mutation_performed",
    "resolution_sha256",
}


def _request_semantic_projection(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict) or not REQUEST_ALLOCATION_IDENTITY_KEYS.issubset(
        request
    ):
        raise ValueError("authority request lacks compiler allocation identities")
    return {
        key: request[key]
        for key in sorted(request)
        if key not in REQUEST_ALLOCATION_IDENTITY_KEYS
    }


def _request_semantic_sha256(request: Any) -> str:
    projection = _request_semantic_projection(request)
    payload = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _operation(request: dict[str, Any]) -> dict[str, str]:
    value = {key: request.get(key) for key in sorted(OPERATION_KEYS)}
    if set(value) != OPERATION_KEYS or any(
        not isinstance(item, str) or not item for item in value.values()
    ):
        raise ValueError("authority decision operation identity is invalid")
    return value


def _operation_key(value: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        value["skill_id"],
        value["skill_version"],
        value["operation_id"],
        value["operation_version"],
    )


def _subject(value: Any, label: str) -> dict[str, str]:
    row = closed_object(value, SUBJECT_KEYS, label)
    normalized = {key: row.get(key) for key in SUBJECT_KEYS}
    if any(
        not isinstance(item, str) or not item for item in normalized.values()
    ) or not SHA256.fullmatch(normalized["digest"]):
        raise ValueError(f"{label} is invalid")
    return normalized


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be RFC3339-compatible") from exc
    if parsed.tzinfo is None or parsed.isoformat() != value:
        raise ValueError(f"{label} must be a normalized timezone-aware timestamp")
    return value


def _singleton_authority_candidate(
    synthesis: dict[str, Any],
) -> dict[str, Any]:
    if (
        synthesis.get("selection_outcome") != "user_escalation"
        or synthesis.get("selected_task_id") is not None
        or synthesis.get("selected_candidate_id") != ""
        or synthesis.get("pack_disposition") != "user_escalation"
    ):
        raise ValueError("authority reentry requires a user_escalation synthesis")
    analysis = synthesis.get("improvement_analysis_manifest")
    lenses = analysis.get("lens_results") if isinstance(analysis, dict) else None
    source_synthesis = analysis.get("synthesis") if isinstance(analysis, dict) else None
    if not isinstance(lenses, list) or len(lenses) != 3:
        raise ValueError("authority reentry requires exactly three derive lenses")
    candidates: list[dict[str, Any]] = []
    for lens in lenses:
        output = lens.get("output") if isinstance(lens, dict) else None
        rows = output.get("candidates") if isinstance(output, dict) else None
        if (
            not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], dict)
        ):
            raise ValueError(
                "authority reentry requires one candidate from every derive lens"
            )
        candidates.append(rows[0])
    first = candidates[0]
    if any(canonical_bytes(row) != canonical_bytes(first) for row in candidates[1:]):
        raise ValueError(
            "authority reentry lens candidates are not canonical-identical"
        )
    candidate_id = first.get("candidate_id")
    if (
        not isinstance(candidate_id, str)
        or not CANDIDATE_ID.fullmatch(candidate_id)
        or first.get("actionability") != "blocked_authority"
        or any(row.get("actionability") != "blocked_authority" for row in candidates)
    ):
        raise ValueError("authority reentry candidate is not authority-blocked")
    union = (
        source_synthesis.get("candidate_union_ids")
        if isinstance(source_synthesis, dict)
        else None
    )
    if union != [candidate_id]:
        raise ValueError("authority reentry requires one exact candidate union")
    if (
        source_synthesis.get("candidate_union_sha256")
        != hashlib.sha256(
            json.dumps(
                union, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
    ):
        raise ValueError("authority reentry candidate union digest differs")
    return first


def _source_predecessor_task_id(source: dict[str, Any]) -> str:
    predecessor = source.get("completed_task_id")
    task_id = source.get("task_id")
    if (
        not isinstance(predecessor, str)
        or not predecessor
        or (task_id is not None and task_id != predecessor)
    ):
        raise ValueError(
            "source derive predecessor task identity is missing or conflicting"
        )
    return predecessor


def _selected_task_id(candidate: dict[str, Any]) -> str:
    candidate_id = str(candidate.get("candidate_id") or "")
    task_id = "task-" + candidate_id.removeprefix("candidate-")
    if not CANDIDATE_ID.fullmatch(candidate_id) or not TASK_ID.fullmatch(task_id):
        raise ValueError("authority reentry candidate cannot derive a task ID")
    return task_id


def _task_markdown(
    *,
    task_id: str,
    source_cycle_id: str,
    source_derive: dict[str, str],
    candidate: dict[str, Any],
    subject: dict[str, str],
    operations: list[dict[str, str]],
    excluded_effects: list[str],
) -> bytes:
    operation_lines = "\n".join(
        "- `"
        + ":".join(
            operation[key]
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        )
        + "`"
        for operation in operations
    )
    excluded_lines = "\n".join(f"- `{item}`" for item in excluded_effects)
    candidate_json = json.dumps(
        candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    text = f"""# Authority-Resolved Successor Task

- Task ID: `{task_id}`
- Source candidate: `{candidate["candidate_id"]}`
- Source cycle: `{source_cycle_id}`
- Source derive ref: `{source_derive["ref"]}`
- Source derive SHA-256: `{source_derive["sha256"]}`

## Candidate Contract

```json
{candidate_json}
```

## Exact Authority Subject

- Kind: `{subject["kind"]}`
- Ref: `{subject["ref"]}`
- Digest: `{subject["digest"]}`
- Revision: `{subject["revision"]}`

## Authorized Operations

{operation_lines}

## Excluded Effects

{excluded_lines}

## Execution Environment

Execute only against the exact authority subject and the operations listed above.
Resolve an independent reservation, verification, and settlement lifecycle for every
effect. Preserve the candidate evidence and validation identities; this task source
does not itself grant authority, accept risk, change goal truth, or supply input.
"""
    return text.encode("utf-8")


def _resolution_body(
    *,
    trigger_binding: dict[str, str],
    synthesis_binding: dict[str, str],
    source_cycle_id: str,
    source_derive: dict[str, str],
    authority_reentry_at: str,
    candidate: dict[str, Any],
    subject: dict[str, str],
    source_authority_request: dict[str, Any],
    decision_entries: list[dict[str, Any]],
    source_approval: dict[str, str],
    root_materialization_ref: str,
    authorized_operations: list[dict[str, str]],
    selected_task_id: str,
    task_source: dict[str, str],
) -> dict[str, Any]:
    core = {
        "schema_version": 1,
        "artifact_kind": "user_escalation_authority_resolution",
        "selection_trigger": trigger_binding,
        "source_selection_synthesis": synthesis_binding,
        "source_cycle_id": source_cycle_id,
        "source_derive": source_derive,
        "source_outcome": "user_escalation",
        "authority_reentry_at": authority_reentry_at,
        "candidate": candidate,
        "candidate_sha256": canonical_sha256(candidate),
        "authority_subject": subject,
        "source_authority_request": source_authority_request,
        "authority_decisions": decision_entries,
        "source_approval": source_approval,
        "root_materialization_ref": root_materialization_ref,
        "authorized_operations": authorized_operations,
        "selected_task_id": selected_task_id,
        "task_source": task_source,
        "not_goal_truth": True,
        "not_authority": True,
        "not_validation_evidence": True,
        "mutation_performed": False,
    }
    resolution_id = "authority-reentry-" + canonical_sha256(core)[:24]
    body = {**core, "resolution_id": resolution_id}
    return {**body, "resolution_sha256": canonical_sha256(body)}


def validate_authority_reentry_resolution_seal(value: Any) -> dict[str, Any]:
    """Validate the closed, self-sealed resolution shape without opening bindings."""

    resolution = closed_object(value, RESOLUTION_KEYS, "authority reentry resolution")
    if (
        resolution.get("schema_version") != 1
        or resolution.get("artifact_kind") != "user_escalation_authority_resolution"
        or resolution.get("source_outcome") != "user_escalation"
        or resolution.get("not_goal_truth") is not True
        or resolution.get("not_authority") is not True
        or resolution.get("not_validation_evidence") is not True
        or resolution.get("mutation_performed") is not False
    ):
        raise ValueError("authority reentry resolution fixed fields are invalid")
    for field in (
        "selection_trigger",
        "source_selection_synthesis",
        "source_derive",
        "source_approval",
        "task_source",
    ):
        normalize_binding(resolution.get(field), field.replace("_", " "))
    _timestamp(resolution.get("authority_reentry_at"), "authority reentry at")
    subject = _subject(resolution.get("authority_subject"), "authority subject")
    source_request = closed_object(
        resolution.get("source_authority_request"),
        SOURCE_AUTHORITY_REQUEST_KEYS,
        "source authority request",
    )
    normalize_binding(source_request.get("decision"), "source authority decision")
    if not all(
        SHA256.fullmatch(str(source_request.get(field) or ""))
        for field in ("request_sha256", "request_semantic_sha256")
    ):
        raise ValueError("source authority request binding is invalid")
    candidate = resolution.get("candidate")
    if (
        not isinstance(candidate, dict)
        or resolution.get("candidate_sha256") != canonical_sha256(candidate)
        or not TASK_ID.fullmatch(str(resolution.get("selected_task_id") or ""))
        or resolution.get("selected_task_id") != _selected_task_id(candidate)
    ):
        raise ValueError("authority reentry candidate binding is invalid")
    operations = resolution.get("authorized_operations")
    decisions = resolution.get("authority_decisions")
    if (
        not isinstance(operations, list)
        or not operations
        or not isinstance(decisions, list)
        or not decisions
    ):
        raise ValueError("authority reentry authority set is empty")
    normalized_operations = [_operation(row) for row in operations]
    if normalized_operations != sorted(
        normalized_operations, key=_operation_key
    ) or len({_operation_key(row) for row in normalized_operations}) != len(
        normalized_operations
    ):
        raise ValueError("authority reentry operations are not a canonical set")
    normalized_decisions: list[dict[str, Any]] = []
    for raw in decisions:
        row = closed_object(raw, DECISION_ENTRY_KEYS, "authority decision entry")
        normalized_decisions.append(
            {
                "decision": normalize_binding(
                    row.get("decision"), "authority decision"
                ),
                "decision_id": row.get("decision_id"),
                "request_sha256": row.get("request_sha256"),
                "request_semantic_sha256": row.get("request_semantic_sha256"),
                "operation": _operation(row.get("operation") or {}),
            }
        )
    if any(
        not SHA256.fullmatch(str(row["request_sha256"] or ""))
        or not SHA256.fullmatch(str(row["request_semantic_sha256"] or ""))
        for row in normalized_decisions
    ):
        raise ValueError("authority reentry decision request binding is invalid")
    if normalized_decisions != decisions:
        raise ValueError("authority reentry decision entries are not canonical")
    core = {
        key: resolution[key]
        for key in RESOLUTION_KEYS
        if key not in {"resolution_id", "resolution_sha256"}
    }
    expected_id = "authority-reentry-" + canonical_sha256(core)[:24]
    body = {**core, "resolution_id": expected_id}
    sealed = {**body, "resolution_sha256": canonical_sha256(body)}
    if resolution != sealed or subject != resolution["authority_subject"]:
        raise ValueError("authority reentry resolution integrity failed")
    return sealed


__all__ = ("validate_authority_reentry_resolution_seal",)
