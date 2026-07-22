"""Integrity, path, and immutable-publication contract for transition plans."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import stat
from typing import Any

from .transition_publication import publish_immutable_file


PLAN_SCHEMA_VERSION = 1
PROSPECTIVE_PLAN_SCHEMA_VERSION = 2
PLAN_KIND = "task_state_transition_plan"
RESULT_SCHEMA_VERSION = 1
PLAN_FIELDS = {
    "schema_version",
    "plan_kind",
    "plan_id",
    "created_at",
    "request",
    "request_sha256",
    "ledger",
    "markdown",
    "artifact_anchors",
    "events",
    "plan_sha256",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _timezone_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a timezone-aware RFC3339 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"{label} must be a timezone-aware RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be a timezone-aware RFC3339 timestamp")
    return value


def validate_transition_request(request: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(request, dict):
        raise ValueError("Task-state transition request must be a JSON object")
    allowed = {
        "schema_version",
        "events",
        "updated_at",
        "render",
        "artifact_sources",
        "external_settlement_kind",
    }
    if set(request) - allowed:
        raise ValueError("Task-state transition request has unsupported fields")
    schema_version = request.get("schema_version", PLAN_SCHEMA_VERSION)
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version not in {PLAN_SCHEMA_VERSION, PROSPECTIVE_PLAN_SCHEMA_VERSION}
    ):
        raise ValueError("Unsupported task-state transition request schema_version")
    if request.get("render", True) is not True:
        raise ValueError("Task-state transition plans require Markdown rendering")
    if schema_version == PLAN_SCHEMA_VERSION:
        if "artifact_sources" in request or "external_settlement_kind" in request:
            raise ValueError("Legacy transition requests cannot declare external settlement")
    else:
        sources = request.get("artifact_sources")
        if (
            request.get("external_settlement_kind") != "selection_publication"
            or not isinstance(sources, list)
            or not sources
        ):
            raise ValueError(
                "Prospective transition requests require selection-publication settlement and artifact sources"
            )
        seen_targets: set[str] = set()
        for row in sources:
            if not isinstance(row, dict) or set(row) != {"target_ref", "source"}:
                raise ValueError("Prospective artifact source is malformed")
            target_ref = row.get("target_ref")
            source = row.get("source")
            if (
                not isinstance(target_ref, str)
                or not target_ref
                or target_ref in seen_targets
                or not isinstance(source, dict)
                or set(source) != {"ref", "sha256"}
                or not isinstance(source.get("ref"), str)
                or not source["ref"]
                or not _is_sha256(source.get("sha256"))
            ):
                raise ValueError("Prospective artifact source binding is invalid")
            seen_targets.add(target_ref)
    if "updated_at" in request:
        _timezone_timestamp(request["updated_at"], "Transition request updated_at")
    events = request.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Transition request requires a non-empty events list")
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Every transition event must be a JSON object")
    return [dict(event) for event in events]


def regular_payload(path: Path, *, missing: bytes | None = None) -> bytes:
    if not path.exists() and not path.is_symlink():
        if missing is not None:
            return missing
        raise ValueError(f"Required file is missing: {path}")
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise ValueError(f"Plan/CAS path must be a regular file: {path}")
    return path.read_bytes()


def workspace_path(root: Path, value: str | Path) -> Path:
    root = root.resolve()
    raw_value = str(value)
    candidate = PurePosixPath(raw_value)
    if (
        not raw_value
        or "\\" in raw_value
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or candidate.as_posix() != raw_value
    ):
        raise ValueError(f"Path must be canonical workspace-relative text: {value}")
    relative = Path(*candidate.parts)
    current = root
    parts = relative.parts
    for offset, part in enumerate(parts):
        current /= part
        if not current.exists() and not current.is_symlink():
            continue
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError(f"Path ancestor must not be a symlink: {value}")
        if offset < len(parts) - 1 and not stat.S_ISDIR(mode):
            raise ValueError(f"Path ancestor must be a directory: {value}")
    return root / relative


def owned_transition_file(
    root: Path,
    directory: str,
    filename: str,
    *,
    create_parent: bool,
) -> Path:
    """Resolve one closed transition-owned file without following symlinks."""

    allowed = {
        "transition_plans",
        "transition_intents",
        "transition_receipts",
        "transition_pending_receipts",
        "transition_no_effect_receipts",
    }
    if directory not in allowed or Path(filename).name != filename or not filename:
        raise ValueError("Invalid task-state transition owned path")
    resolved_root = root.resolve()
    if create_parent:
        from .transition_publication import ensure_owned_transition_directory

        ensure_owned_transition_directory(resolved_root, directory)
    current = resolved_root
    for part in (".task", directory):
        current /= part
        if current.exists() or current.is_symlink():
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ValueError(
                    "Task-state transition owned root must be a regular directory"
                )
    path = current / filename
    if path.exists() or path.is_symlink():
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise ValueError("Task-state transition owned file must be regular")
    return path


def canonical_plan_output_path(root: Path, value: str | Path) -> Path:
    raw_value = str(value)
    candidate = PurePosixPath(raw_value)
    parts = candidate.parts
    if (
        candidate.is_absolute()
        or "\\" in raw_value
        or len(parts) != 3
        or parts[:2] != (".task", "transition_plans")
        or candidate.as_posix() != raw_value
        or not parts[2].endswith(".json")
    ):
        raise ValueError(
            "Task-state plan output must be an exact canonical "
            ".task/transition_plans/<file>.json path"
        )
    return owned_transition_file(
        root, "transition_plans", parts[-1], create_parent=True
    )


def publish_immutable(path: Path, payload: bytes) -> bool:
    return publish_immutable_file(path, payload)


def _validate_plan_projections(plan: dict[str, Any], events: list[Any]) -> None:
    ledger = plan.get("ledger") if isinstance(plan.get("ledger"), dict) else {}
    markdown = plan.get("markdown") if isinstance(plan.get("markdown"), dict) else {}
    if (
        set(ledger) != {
            "path",
            "before_sha256",
            "after_sha256",
            "before_size",
            "before_event_count",
            "before_events_sha256",
            "event_count",
        }
        or ledger.get("path") != ".task/index.jsonl"
        or not _is_sha256(ledger.get("before_sha256"))
        or not _is_sha256(ledger.get("after_sha256"))
        or not isinstance(ledger.get("before_size"), int)
        or isinstance(ledger.get("before_size"), bool)
        or ledger.get("before_size") < 0
        or not isinstance(ledger.get("before_event_count"), int)
        or isinstance(ledger.get("before_event_count"), bool)
        or ledger.get("before_event_count") < 0
        or not _is_sha256(ledger.get("before_events_sha256"))
        or not isinstance(ledger.get("event_count"), int)
        or isinstance(ledger.get("event_count"), bool)
        or ledger.get("event_count") != len(events)
    ):
        raise ValueError("Task-state transition plan ledger binding is malformed")
    if (
        set(markdown) != {"path", "before_sha256", "after_sha256", "render"}
        or markdown.get("path") != ".task/index.md"
        or (
            markdown.get("before_sha256") is not None
            and not _is_sha256(markdown.get("before_sha256"))
        )
        or not _is_sha256(markdown.get("after_sha256"))
        or markdown.get("render") is not True
    ):
        raise ValueError("Task-state transition plan Markdown binding is malformed")


def _validated_artifact_anchors(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    anchors = plan.get("artifact_anchors")
    if not isinstance(anchors, list):
        raise ValueError("Task-state transition plan lacks artifact anchors")
    anchors_by_path: dict[str, dict[str, Any]] = {}
    for anchor in anchors:
        if not isinstance(anchor, dict) or set(anchor) != {
            "path",
            "before_sha256",
            "expected_sha256",
            "expectation",
        }:
            raise ValueError("Task-state transition plan artifact anchor is malformed")
        if not isinstance(anchor["path"], str) or not anchor["path"]:
            raise ValueError("Task-state transition plan artifact anchor lacks a path")
        if anchor["path"] in anchors_by_path:
            raise ValueError("Task-state transition plan has duplicate artifact anchors")
        anchors_by_path[anchor["path"]] = anchor
        if anchor["expectation"] not in {
            "planned_content_sha256",
            "unchanged_from_plan",
            "prospective_source_sha256",
        }:
            raise ValueError("Task-state transition plan artifact expectation is invalid")
        for field in ("before_sha256", "expected_sha256"):
            value = anchor[field]
            if value is not None and not _is_sha256(value):
                raise ValueError("Task-state transition plan artifact digest is invalid")
        if (
            anchor["expectation"] == "unchanged_from_plan"
            and anchor["expected_sha256"] != anchor["before_sha256"]
        ):
            raise ValueError("Unbound artifact anchor must remain unchanged from planning")
    return anchors_by_path


def _validate_anchor_coverage(
    anchors_by_path: dict[str, dict[str, Any]], events: list[Any]
) -> None:
    final_upserts = {
        event["path"]: event
        for event in events
        if event.get("event") == "upsert" and isinstance(event.get("path"), str)
    }
    if set(anchors_by_path) != set(final_upserts):
        raise ValueError(
            "Task-state transition plan artifact anchors must exactly cover final upsert paths"
        )
    for path, event in final_upserts.items():
        anchor = anchors_by_path[path]
        expected = event.get("content_sha256")
        if expected is not None:
            if not _is_sha256(expected):
                raise ValueError("Task-state transition event content digest is invalid")
            if (
                anchor["expectation"]
                not in {"planned_content_sha256", "prospective_source_sha256"}
                or anchor["expected_sha256"] != expected
            ):
                raise ValueError(
                    "Task-state transition artifact anchor does not bind planned content"
                )
        elif anchor["expectation"] != "unchanged_from_plan":
            raise ValueError(
                "Task-state transition unbound artifact must retain its planning anchor"
            )


def validate_transition_plan(plan: dict[str, Any]) -> None:
    if set(plan) != PLAN_FIELDS:
        raise ValueError("Task-state transition plan fields are malformed")
    if (
        not isinstance(plan.get("schema_version"), int)
        or isinstance(plan.get("schema_version"), bool)
        or plan.get("schema_version")
        not in {PLAN_SCHEMA_VERSION, PROSPECTIVE_PLAN_SCHEMA_VERSION}
        or plan.get("plan_kind") != PLAN_KIND
    ):
        raise ValueError("Unsupported task-state transition plan")
    supplied = plan.get("plan_sha256")
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if supplied != sha256_bytes(canonical_bytes(body)):
        raise ValueError("Task-state transition plan digest mismatch")
    request = plan.get("request")
    validate_transition_request(request)
    if plan.get("schema_version") != request.get("schema_version", PLAN_SCHEMA_VERSION):
        raise ValueError("Task-state transition plan/request schema mismatch")
    request_sha256 = plan.get("request_sha256")
    if (
        not _is_sha256(request_sha256)
        or request_sha256 != sha256_bytes(canonical_bytes(request))
    ):
        raise ValueError("Task-state transition request digest mismatch")
    created_at = _timezone_timestamp(
        plan.get("created_at"), "Transition plan created_at"
    )
    if request.get("updated_at") is not None and request["updated_at"] != created_at:
        raise ValueError("Task-state transition request timestamp binding mismatch")
    plan_id = plan.get("plan_id")
    if (
        not isinstance(plan_id, str)
        or not plan_id.startswith("transition-")
        or len(plan_id) != len("transition-") + 32
        or any(character not in "0123456789abcdef" for character in plan_id[11:])
    ):
        raise ValueError("Task-state transition plan_id is malformed")
    identity = {
        "request_sha256": request_sha256,
        "ledger_sha256": (
            plan["ledger"].get("before_sha256")
            if isinstance(plan.get("ledger"), dict)
            else None
        ),
        "updated_at": created_at,
    }
    if plan_id != f"transition-{sha256_bytes(canonical_bytes(identity))[:32]}":
        raise ValueError("Task-state transition plan_id derivation mismatch")
    events = plan.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Task-state transition plan has no events")
    if any(
        event.get("transition_plan_id") != plan.get("plan_id") for event in events
    ):
        raise ValueError("Task-state transition plan event binding mismatch")
    if any(event.get("updated_at") != plan.get("created_at") for event in events):
        raise ValueError("Task-state transition plan timestamp binding mismatch")
    _validate_plan_projections(plan, events)
    anchors = _validated_artifact_anchors(plan)
    _validate_anchor_coverage(anchors, events)
    if plan.get("schema_version") == PROSPECTIVE_PLAN_SCHEMA_VERSION:
        source_by_target = {
            row["target_ref"]: row["source"]
            for row in request["artifact_sources"]
        }
        prospective = {
            path: anchor
            for path, anchor in anchors.items()
            if anchor["expectation"] == "prospective_source_sha256"
        }
        if set(prospective) != set(source_by_target):
            raise ValueError(
                "Prospective transition sources must exactly cover prospective anchors"
            )
        for path, anchor in prospective.items():
            if source_by_target[path]["sha256"] != anchor["expected_sha256"]:
                raise ValueError("Prospective transition source digest mismatch")


def load_transition_plan(
    root: Path, path_value: str | Path
) -> tuple[Path, dict[str, Any], str]:
    root = root.resolve()
    path = workspace_path(root, path_value)
    relative = path.relative_to(root)
    if (
        len(relative.parts) != 3
        or relative.parts[:2] != (".task", "transition_plans")
        or not relative.name.endswith(".json")
        or path
        != owned_transition_file(
            root,
            "transition_plans",
            relative.name,
            create_parent=False,
        )
    ):
        raise ValueError(
            "Task-state transition plan must be a canonical transition_plans file"
        )
    payload = regular_payload(path)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid task-state transition plan: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError("Task-state transition plan must be a JSON object")
    validate_transition_plan(value)
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError("Task-state transition plan file bytes are not canonical")
    if relative.name != f"{value['plan_id']}.json":
        raise ValueError(
            "Task-state transition plan filename must equal its plan_id"
        )
    return path, value, sha256_bytes(payload)


def receipt_for_plan(
    plan: dict[str, Any], plan_ref: str, plan_file_sha256: str
) -> dict[str, Any]:
    body = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "receipt_kind": "task_state_transition_apply_receipt",
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "applied_at": plan["created_at"],
        "ledger_after_sha256": plan["ledger"]["after_sha256"],
        "markdown_after_sha256": plan["markdown"]["after_sha256"],
        "event_count": plan["ledger"]["event_count"],
    }
    return {
        **body,
        "receipt_content_sha256": sha256_bytes(canonical_bytes(body)),
    }


def receipt_status(path: Path, expected: dict[str, Any]) -> tuple[str, str | None]:
    if not path.exists() and not path.is_symlink():
        return "missing", None
    payload = regular_payload(path)
    expected_payload = canonical_bytes(expected) + b"\n"
    if payload != expected_payload:
        return "conflict", sha256_bytes(payload)
    return "current", sha256_bytes(payload)
