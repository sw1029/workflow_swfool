"""Content-addressed result publication through the existing cycle ledger."""

from __future__ import annotations

from pathlib import Path
import hashlib
from typing import Any

from ..cycle_ledger import (
    append_event,
    cycle_dir,
    immutable_write_bytes,
    ledger_path,
    read_events,
    read_events_raw,
    write_current,
)
from ..ledger.support import normalize_list, rel_path
from ..ledger.result_hydration import (
    COMPACT_COMPILER_METRIC_FIELDS,
    COMPACT_RESULT_EVENT_KIND,
    hydrate_result_event,
    project_result_scalars,
)
from .contracts import (
    canonical_bytes,
    canonical_sha256,
    preparation_binding_sha256,
)
from .artifact_store import cas_write_receipt, merge_compiler_io_metrics


def _compact_metrics(value: dict[str, Any] | None) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for key, item in (value or {}).items():
        if key not in COMPACT_COMPILER_METRIC_FIELDS or item is None:
            continue
        if isinstance(item, bool):
            metrics[key] = item
        elif isinstance(item, int) and item >= 0:
            metrics[key] = item
        elif isinstance(item, str) and len(item.encode("utf-8")) <= 512:
            metrics[key] = item
    return metrics


def result_path(root: Path, cycle_id: str, target: str, digest: str) -> Path:
    return cycle_dir(root, cycle_id) / "packets" / f"result-{target}-{digest}.json"


def result_event(
    preparation: dict[str, Any],
    result: dict[str, Any],
    result_ref: str,
    result_sha256: str,
    compiler_metrics: dict[str, Any] | None = None,
    input_bindings_sha256: str | None = None,
) -> dict[str, Any]:
    preparation_binding = preparation_binding_sha256(preparation)
    event_identity = {
        "preparation_id": preparation["preparation_id"],
        "result_sha256": result_sha256,
    }
    event_id = (
        "stage-"
        + str(preparation["target"])
        + "-"
        + canonical_sha256(event_identity)[:32]
    )
    if preparation.get("schema_version") == 1:
        legacy = dict(result)
        legacy.update(
            {
                "step": preparation["target"],
                "status": "completed",
                "event_id": event_id,
                "reason": "validated compiled stage result",
                "preparation_id": preparation["preparation_id"],
                "preparation_binding_sha256": preparation_binding,
                "result_artifact_ref": result_ref,
                "result_artifact_sha256": result_sha256,
            }
        )
        legacy["artifacts"] = normalize_list(result.get("artifacts"), result_ref)
        return legacy
    payload = canonical_bytes(result) + b"\n"
    raw_sha256 = hashlib.sha256(payload).hexdigest()
    scalars = project_result_scalars(result)
    event = {
        "format_version": 2,
        "event_kind": COMPACT_RESULT_EVENT_KIND,
        "step": preparation["target"],
        "status": "completed",
        "event_id": event_id,
        "reason": "validated compiled stage result",
        "preparation_id": preparation["preparation_id"],
        "preparation_binding_sha256": preparation_binding,
        "input_bindings_sha256": input_bindings_sha256 or canonical_sha256({}),
        "result_artifact_ref": result_ref,
        "result_artifact_sha256": result_sha256,
        "result_artifact_raw_sha256": raw_sha256,
        "result_artifact_binding": {
            "ref": result_ref,
            "sha256": raw_sha256,
            "size_bytes": len(payload),
            "body_sha256": result_sha256,
        },
        "compiler_metrics": _compact_metrics(compiler_metrics),
        "result_projection": scalars,
        "artifacts": [result_ref],
        **scalars,
    }
    event["compiler_metrics"]["compact_payload_bytes"] = (
        len(canonical_bytes(event)) + 1
    )
    return event


def existing_publication(
    root: Path,
    cycle_id: str,
    target: str,
    preparation: dict[str, Any],
    result: dict[str, Any],
    digest: str,
    input_bindings: dict[str, Any] | None = None,
    *,
    repair_projection: bool = False,
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
    if event.get("format_version") == 2 and event.get(
        "input_bindings_sha256"
    ) != canonical_sha256(input_bindings or {}):
        raise ValueError("replay exact stage input bindings do not match publication")
    if not path.is_file() or path.read_bytes() != expected:
        raise ValueError(
            "published stage event has missing or conflicting result artifact"
        )
    raw_event = next(
        item
        for item in read_events_raw(root, cycle_id)
        if item.get("event_id") == event_id
    )
    if repair_projection:
        write_current(root, cycle_id)
    return {
        "event": event,
        "event_duplicate": True,
        "result_artifact_ref": rel_path(root, path),
        "ledger_path": rel_path(root, ledger_path(root, cycle_id)),
        "ledger_event_bytes": len(canonical_bytes(raw_event)) + 1,
        "result_artifact_bytes": len(expected),
        "compiler_metrics": dict(raw_event.get("compiler_metrics") or {}),
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
    compiler_metrics: dict[str, Any] | None = None,
    input_bindings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = str(preparation["target"])
    path = result_path(root, cycle_id, target, digest)
    relative = rel_path(root, path)
    existing = existing_publication(
        root,
        cycle_id,
        target,
        preparation,
        result,
        digest,
        input_bindings,
        repair_projection=True,
    )
    if existing is not None:
        return existing
    payload = canonical_bytes(result) + b"\n"
    mutation_performed = immutable_write_bytes(path, payload)
    result_write_receipt = cas_write_receipt(len(payload), mutation_performed)
    persisted_metrics = merge_compiler_io_metrics(
        compiler_metrics, result_write_receipt
    )
    persisted_metrics["result_bytes"] = len(payload)
    publication = append_event(
        root,
        cycle_id,
        result_event(
            preparation,
            result,
            relative,
            digest,
            persisted_metrics,
            canonical_sha256(input_bindings or {}),
        ),
    )
    hydrated = hydrate_result_event(root, cycle_id, publication["event"])
    return {
        "event": hydrated,
        "event_duplicate": bool(publication.get("event_duplicate")),
        "ledger_path": publication["ledger_path"],
        "result_artifact_ref": relative,
        "ledger_event_bytes": len(canonical_bytes(publication["event"])) + 1,
        "result_artifact_bytes": len(payload),
        "result_write_receipt": result_write_receipt,
        "compiler_metrics": dict(publication["event"].get("compiler_metrics") or {}),
    }


__all__ = [
    "existing_publication",
    "published_preparation",
    "publish_result",
    "replay_mismatch",
    "result_event",
    "result_path",
]
