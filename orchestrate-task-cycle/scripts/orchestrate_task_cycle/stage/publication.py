"""Content-addressed result publication through the existing cycle ledger."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any

from ..cycle_ledger import (
    append_event as _append_legacy_event,
    cycle_dir,
    immutable_write_bytes,
    ledger_path,
    read_events,
    read_events_raw,
    write_current,
)
from ..ledger.compiled_events import append_compiled_stage_result_binding
from ..ledger.compiler_binding import (
    CompiledEventBinding,
    compile_stage_result_binding,
)
from ..ledger.support import ledger_lock, rel_path
from ..ledger.support import read_initialization_metadata
from ..ledger.workflow_contract import workflow_contract_state
from ..ledger.result_hydration import hydrate_result_event
from ..ledger.stage_result_compiler import (
    derive_stage_result_event,
    preflight_stage_result_publication,
)
from .contracts import (
    canonical_bytes,
    canonical_sha256,
    preparation_binding_sha256,
    validate_preparation,
)
from .artifact_store import cas_write_receipt, merge_compiler_io_metrics
from .protocol import cycle_preparation_version


def _append_compiled_result_binding(
    root: Path, cycle_id: str, binding: CompiledEventBinding
) -> dict[str, Any]:
    """Patchable enforced-cycle seam backed by exact result CAS revalidation."""

    metadata = read_initialization_metadata(root, cycle_id)
    contract_state = workflow_contract_state(metadata)
    if contract_state != "enforced":
        raise ValueError(
            "compiled result binding publication requires an enforced cycle"
        )
    return append_compiled_stage_result_binding(root, cycle_id, binding)


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
    return derive_stage_result_event(
        preparation,
        result,
        result_ref,
        result_sha256,
        compiler_metrics,
        {},
        input_bindings_sha256=input_bindings_sha256,
    )


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
    *,
    max_files: int = 12,
    max_paths: int = 40,
) -> dict[str, Any]:
    preparation = validate_preparation(preparation)
    if preparation.get("cycle_id") != cycle_id:
        raise ValueError("stage result preparation belongs to another cycle")
    if not isinstance(result, dict) or canonical_sha256(result) != digest:
        raise ValueError("stage result digest does not match canonical result bytes")
    metadata = read_initialization_metadata(root, cycle_id)
    state = workflow_contract_state(metadata)
    if state in {"historical_v1_read_only", "historical_v2_read_only", "invalid"}:
        raise ValueError(
            "non-enforced protocol-v2 or invalid cycles are read-only; "
            "stage results cannot be published"
        )
    if state == "enforced":
        cycle_preparation_version(
            root, cycle_id, int(preparation["schema_version"])
        )
    mutation_scope = (
        ledger_lock(root, cycle_id, exclusive=True)
        if state == "enforced"
        else nullcontext()
    )
    with mutation_scope:
        target = str(preparation["target"])
        path = result_path(root, cycle_id, target, digest)
        relative = rel_path(root, path)
        previous_events = (
            read_events_raw(root, cycle_id) if state == "enforced" else []
        )
        if state == "enforced":
            preflight_stage_result_publication(
                root,
                cycle_id,
                preparation,
                result,
                input_bindings,
                {"max_files": max_files, "max_paths": max_paths},
                previous_events,
            )
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
        result_write_receipt = cas_write_receipt(
            len(payload), mutation_performed
        )
        persisted_metrics = merge_compiler_io_metrics(
            compiler_metrics, result_write_receipt
        )
        persisted_metrics["result_bytes"] = len(payload)
        if state == "enforced":
            binding = compile_stage_result_binding(
                preparation,
                result,
                relative,
                digest,
                persisted_metrics,
                input_bindings,
                {"max_files": max_files, "max_paths": max_paths},
                previous_events,
            )
            publication = _append_compiled_result_binding(
                root, cycle_id, binding
            )
        else:
            event = result_event(
                preparation,
                result,
                relative,
                digest,
                persisted_metrics,
                canonical_sha256(input_bindings or {}),
            )
            publication = _append_legacy_event(root, cycle_id, event)
        hydrated = hydrate_result_event(
            root, cycle_id, publication["event"]
        )
        output = {
            "event": hydrated,
            "event_duplicate": bool(publication.get("event_duplicate")),
            "ledger_path": publication["ledger_path"],
            "result_artifact_ref": relative,
            "ledger_event_bytes": len(canonical_bytes(publication["event"])) + 1,
            "result_artifact_bytes": len(payload),
            "result_write_receipt": result_write_receipt,
            "compiler_metrics": dict(
                publication["event"].get("compiler_metrics") or {}
            ),
        }
        if publication.get("workflow_contract_warning") is not None:
            output["workflow_contract_warning"] = publication[
                "workflow_contract_warning"
            ]
        return output


__all__ = [
    "existing_publication",
    "published_preparation",
    "publish_result",
    "replay_mismatch",
    "result_event",
    "result_path",
]
