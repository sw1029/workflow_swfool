"""Content-addressed result publication through the existing cycle ledger."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cycle_ledger import (
    append_event,
    cycle_dir,
    immutable_write_bytes,
    ledger_path,
    read_events,
)
from ..ledger.support import normalize_list, rel_path
from .contracts import (
    canonical_bytes,
    canonical_sha256,
    preparation_binding_sha256,
)


def result_path(root: Path, cycle_id: str, target: str, digest: str) -> Path:
    return cycle_dir(root, cycle_id) / "packets" / f"result-{target}-{digest}.json"


def result_event(
    preparation: dict[str, Any],
    result: dict[str, Any],
    result_ref: str,
    result_sha256: str,
) -> dict[str, Any]:
    preparation_binding = preparation_binding_sha256(preparation)
    event_identity = {
        "preparation_id": preparation["preparation_id"],
        "result_sha256": result_sha256,
    }
    event = dict(result)
    event.update(
        {
            "step": preparation["target"],
            "status": "completed",
            "event_id": "stage-"
            + str(preparation["target"])
            + "-"
            + canonical_sha256(event_identity)[:32],
            "reason": "validated compiled stage result",
            "preparation_id": preparation["preparation_id"],
            "preparation_binding_sha256": preparation_binding,
            "result_artifact_ref": result_ref,
            "result_artifact_sha256": result_sha256,
        }
    )
    event["artifacts"] = normalize_list(result.get("artifacts"), result_ref)
    return event


def existing_publication(
    root: Path,
    cycle_id: str,
    target: str,
    preparation: dict[str, Any],
    result: dict[str, Any],
    digest: str,
) -> dict[str, Any] | None:
    path = result_path(root, cycle_id, target, digest)
    expected = canonical_bytes(result) + b"\n"
    event_id = result_event(preparation, result, rel_path(root, path), digest)[
        "event_id"
    ]
    event = next(
        (
            item
            for item in read_events(root, cycle_id)
            if item.get("event_id") == event_id
        ),
        None,
    )
    if event is None:
        return None
    if not path.is_file() or path.read_bytes() != expected:
        raise ValueError(
            "published stage event has missing or conflicting result artifact"
        )
    return {
        "event": event,
        "event_duplicate": True,
        "result_artifact_ref": rel_path(root, path),
        "ledger_path": rel_path(root, ledger_path(root, cycle_id)),
    }


def published_preparation(
    root: Path,
    cycle_id: str,
    preparation: dict[str, Any],
) -> bool:
    preparation_id = preparation.get("preparation_id")
    expected_binding = preparation_binding_sha256(preparation)
    matches = [
        event
        for event in read_events(root, cycle_id)
        if event.get("preparation_id") == preparation_id
    ]
    if not matches:
        return False
    if any(
        event.get("preparation_binding_sha256") != expected_binding for event in matches
    ):
        raise ValueError(
            "published preparation binding conflicts with supplied content"
        )
    return True


def replay_mismatch(preparation: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "block",
        "stop_reason": "rejected_result",
        "preparation_id": preparation["preparation_id"],
        "reason": "replay judgment does not match the published result",
        "applied": False,
    }


def publish_result(
    root: Path,
    cycle_id: str,
    preparation: dict[str, Any],
    result: dict[str, Any],
    digest: str,
) -> dict[str, Any]:
    target = str(preparation["target"])
    path = result_path(root, cycle_id, target, digest)
    relative = rel_path(root, path)
    immutable_write_bytes(path, canonical_bytes(result) + b"\n")
    publication = append_event(
        root,
        cycle_id,
        result_event(preparation, result, relative, digest),
    )
    return {
        "event": publication["event"],
        "event_duplicate": bool(publication.get("event_duplicate")),
        "ledger_path": publication["ledger_path"],
        "result_artifact_ref": relative,
    }


__all__ = [
    "existing_publication",
    "published_preparation",
    "publish_result",
    "replay_mismatch",
    "result_event",
    "result_path",
]
