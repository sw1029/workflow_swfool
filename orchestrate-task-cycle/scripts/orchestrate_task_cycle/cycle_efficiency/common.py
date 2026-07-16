from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


TRACE_LABEL_RE = re.compile(
    r"(?:^|[-_:])(cycle|task|run|gen|generation|v)[-_:]?(?:\d+|[0-9a-f]{6,})|20\d{6,}",
    re.IGNORECASE,
)
CYCLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
OPAQUE_ID_MAX_LENGTH = 128
INDEPENDENT_EVIDENCE_STATUSES = {"independent", "independently_verified"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def deep_get(data: Any, path: str) -> Any:
    current = data
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "yes",
            "1",
            "present",
            "produced",
            "changed",
        }
    if isinstance(value, (list, dict)):
        return bool(value)
    return False


def first_present(event: dict[str, Any], paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = deep_get(event, path) if "." in path else event.get(path)
        if (
            value is None
            or (isinstance(value, (list, dict)) and not value)
            or (isinstance(value, str) and not value.strip())
        ):
            continue
        return value
    return None


def bounded_opaque_id(value: Any) -> str | None:
    """Accept only bounded scalar identifiers; never stringify containers."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > OPAQUE_ID_MAX_LENGTH:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        return None
    return text


def is_metadata_only(event: dict[str, Any]) -> bool:
    metadata_only = first_present(
        event,
        (
            "metadata_only",
            "output_delta.metadata_only",
            "output_delta_gate.metadata_only",
        ),
    )
    produced = first_present(
        event,
        (
            "produced_domain_delta",
            "output_delta.produced_domain_delta",
            "output_delta_gate.produced_domain_delta",
        ),
    )
    effective = first_present(
        event,
        (
            "effective_progress_kind",
            "output_delta.effective_progress_kind",
            "output_delta_gate.effective_progress_kind",
        ),
    )
    progress_kind = first_present(
        event, ("progress_kind", "selected_progress_kind", "expected_progress_kind")
    )
    if boolish(metadata_only):
        return True
    if produced is not None and not boolish(produced):
        return True
    return str(effective or progress_kind).lower() == "governance_only"


def stable_scope_value(value: Any) -> str:
    raw = bounded_opaque_id(value)
    if raw is None:
        return ""
    text = TRACE_LABEL_RE.sub("", raw.lower())
    normalized = re.sub(r"[-_:]+", "-", text).strip("-")
    return normalized if bounded_opaque_id(normalized) is not None else ""


def family_scope(event: dict[str, Any]) -> dict[str, str]:
    return {
        "goal_axis": stable_scope_value(
            first_present(event, ("goal_axis", "profile_scope.goal_axis"))
        ),
        "root_family_key": stable_scope_value(
            first_present(
                event,
                (
                    "root_family_key",
                    "blocker_root_family",
                    "profile_scope.root_family_key",
                ),
            )
        ),
        "producer_lineage": stable_scope_value(
            first_present(event, ("producer_lineage", "profile_scope.producer_lineage"))
        ),
        "artifact_class": stable_scope_value(
            first_present(
                event,
                (
                    "observed_artifact_class",
                    "artifact_class",
                    "profile_scope.artifact_class",
                ),
            )
        ),
        "decision_lane": stable_scope_value(
            first_present(
                event,
                (
                    "current_decision_lane",
                    "decision_lane",
                    "profile_scope.decision_lane",
                ),
            )
        ),
        "input_cohort": stable_scope_value(
            first_present(event, ("input_cohort", "profile_scope.input_cohort"))
        ),
    }


def same_family_scope(event: dict[str, Any], scope: dict[str, str]) -> bool:
    candidate = family_scope(event)
    return all(candidate.get(key) == value for key, value in scope.items())


def execution_scope(event: dict[str, Any]) -> dict[str, str]:
    """Minimum producer-run scope; taxonomy and values remain adapter-owned."""
    return {
        "goal_axis": stable_scope_value(
            first_present(event, ("goal_axis", "profile_scope.goal_axis"))
        ),
        "producer_lineage": stable_scope_value(
            first_present(event, ("producer_lineage", "profile_scope.producer_lineage"))
        ),
        "artifact_class": stable_scope_value(
            first_present(
                event,
                (
                    "observed_artifact_class",
                    "artifact_class",
                    "profile_scope.artifact_class",
                ),
            )
        ),
        "decision_lane": stable_scope_value(
            first_present(
                event,
                (
                    "current_decision_lane",
                    "decision_lane",
                    "profile_scope.decision_lane",
                ),
            )
        ),
    }


def same_execution_scope(event: dict[str, Any], scope: dict[str, str]) -> bool:
    candidate = execution_scope(event)
    return all(candidate.get(key) == value for key, value in scope.items())


def fresh_run_id(event: dict[str, Any]) -> str | None:
    if boolish(
        first_present(event, ("replayed", "run_replayed", "carried_forward_run"))
    ):
        return None
    return bounded_opaque_id(
        first_present(
            event, ("run_id", "execution.run_id", "run.run_id", "fresh_run_id")
        )
    )


def _independent_status(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in INDEPENDENT_EVIDENCE_STATUSES
    if not isinstance(value, dict):
        return False
    status = first_present(
        value, ("evidence_provenance", "provenance", "status", "evaluation_status")
    )
    return (
        isinstance(status, str)
        and status.strip().lower() in INDEPENDENT_EVIDENCE_STATUSES
    )


def _axis_bound_independent_evidence(value: Any, goal_axis: str) -> bool:
    """Consume generic provenance only when its row/key names the current goal axis."""
    if isinstance(value, dict):
        row_axis = stable_scope_value(
            first_present(value, ("goal_axis", "goal_axis_id", "axis_id"))
        )
        if row_axis:
            return row_axis == goal_axis and _independent_status(value)
        return any(
            stable_scope_value(raw_axis) == goal_axis and _independent_status(row)
            for raw_axis, row in value.items()
        )
    if isinstance(value, list):
        return any(
            isinstance(row, dict)
            and stable_scope_value(
                first_present(row, ("goal_axis", "goal_axis_id", "axis_id"))
            )
            == goal_axis
            and _independent_status(row)
            for row in value
        )
    return False


def semantic_goal_movement(
    event: dict[str, Any], current_goal_axis: str | None = None
) -> bool:
    if is_metadata_only(event):
        return False
    event_axis = stable_scope_value(
        first_present(event, ("goal_axis", "profile_scope.goal_axis"))
    )
    expected_axis = (
        stable_scope_value(current_goal_axis)
        if current_goal_axis is not None
        else event_axis
    )
    if not event_axis or not expected_axis or event_axis != expected_axis:
        return False
    provenance = first_present(
        event, ("semantic_movement_evidence_class", "semantic_evidence_provenance")
    )
    independent = boolish(event.get("independent_semantic_evidence")) or (
        isinstance(provenance, str) and _independent_status(provenance)
    )
    if isinstance(provenance, (dict, list)):
        independent = independent or _axis_bound_independent_evidence(
            provenance, expected_axis
        )
    independent = independent or _axis_bound_independent_evidence(
        event.get("evidence_provenance"), expected_axis
    )
    verified_fields = event.get("independently_verified_fields")
    if isinstance(verified_fields, (list, tuple, set)):
        independent = independent or any(
            stable_scope_value(field) == expected_axis for field in verified_fields
        )
    if fresh_run_id(event) is None or not independent:
        return False
    authoritative = first_present(
        event, ("authoritative_semantic_progress", "semantic_progress_authoritative")
    )
    if authoritative is not None:
        return boolish(authoritative)
    produced = first_present(
        event, ("produced_domain_delta", "output_delta.produced_domain_delta")
    )
    changed = first_present(
        event, ("changed_vs_previous", "output_delta.changed_vs_previous")
    )
    semantic = first_present(
        event, ("semantic_progress", "output_delta.semantic_progress")
    )
    return boolish(produced) and boolish(changed) and boolish(semantic)


def cycle_groups(
    events: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for index, event in enumerate(events):
        cycle_id = (
            bounded_opaque_id(event.get("cycle_id"))
            or bounded_opaque_id(event.get("event_id"))
            or f"event_{index + 1}"
        )
        if cycle_id not in groups:
            groups[cycle_id] = []
            order.append(cycle_id)
        groups[cycle_id].append(event)
    return [(cycle_id, groups[cycle_id]) for cycle_id in order]


def current_cycle_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not events:
        return []
    latest_cycle_id = bounded_opaque_id(events[-1].get("cycle_id"))
    if not latest_cycle_id:
        return list(events)
    selected = [
        event
        for event in events
        if bounded_opaque_id(event.get("cycle_id")) == latest_cycle_id
    ]
    return selected or list(events)


def artifact_payload_identity(ref: dict[str, Any]) -> tuple[str, str] | None:
    path_or_store_ref = str(ref.get("path") or ref.get("store_ref") or "").strip()
    sha256 = str(ref.get("sha256") or ref.get("artifact_sha256") or "").strip().lower()
    return (
        (path_or_store_ref, sha256)
        if path_or_store_ref and re.fullmatch(r"[0-9a-f]{64}", sha256)
        else None
    )


def artifact_ref_identity(ref: dict[str, Any]) -> str:
    payload_identity = artifact_payload_identity(ref)
    return (
        json.dumps(payload_identity, ensure_ascii=False, separators=(",", ":"))
        if payload_identity is not None
        else ""
    )


def collect_events(root: Path, cycle_id: str | None) -> list[dict[str, Any]]:
    resolved_root = root.resolve()
    cycle_root = (resolved_root / ".task" / "cycle").resolve(strict=False)
    try:
        cycle_root.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            "cycle profile ledger root escapes the workspace through a symlink"
        ) from exc
    if cycle_id:
        if not CYCLE_ID_PATTERN.fullmatch(cycle_id):
            raise ValueError(
                "cycle_id must be one path-safe token of at most 128 characters"
            )
        cycle_path = (cycle_root / cycle_id).resolve(strict=False)
        try:
            cycle_path.relative_to(cycle_root)
        except ValueError as exc:
            raise ValueError(
                "cycle profile path escapes .task/cycle through a symlink"
            ) from exc
        return read_jsonl(cycle_path / "stage.jsonl")
    events: list[dict[str, Any]] = []
    for path in sorted(cycle_root.glob("*/stage.jsonl")) if cycle_root.is_dir() else []:
        try:
            path.resolve().relative_to(cycle_root)
        except ValueError as exc:
            raise ValueError(
                "cycle profile ledger path escapes .task/cycle through a symlink"
            ) from exc
        events.extend(read_jsonl(path))
    return events


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
