"""Gate deterministic predictions before creating any persistent effect."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..ledger.support import ledger_lock, read_initialization_metadata
from ..ledger.workflow_contract import require_cycle_mutation_contract
from .contracts import require_expected_preparation


def _predict_and_preflight(
    root: Path,
    preparation: dict[str, Any],
    *,
    max_files: int,
    max_paths: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from .deterministic_dispatch import predict_deterministic
    from .v2_service import _preflight_deterministic_submission

    prediction = predict_deterministic(
        root,
        preparation,
        max_files=max_files,
        max_paths=max_paths,
    )
    if prediction.get("status") == "block":
        return prediction, prediction
    preflight = _preflight_deterministic_submission(
        root,
        preparation,
        prediction,
        max_files=max_files,
        max_paths=max_paths,
    )
    return prediction, preflight


def _commit_preflighted(
    root: Path,
    preparation: dict[str, Any],
    prediction: dict[str, Any],
    preflight: dict[str, Any],
    *,
    max_files: int,
    max_paths: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from .deterministic_commit import commit_deterministic_gated
    from .service import prepare_stage, submit_stage

    persisted = prepare_stage(
        root,
        str(preparation["cycle_id"]),
        str(preparation["target"]),
        workflow_mode=str(preparation["workflow_mode"]),
        max_files=max_files,
        max_paths=max_paths,
        preparation_schema_version=int(preparation["schema_version"]),
        persist_compiler_artifacts=True,
    )
    require_expected_preparation(preparation, persisted)
    committed = commit_deterministic_gated(
        root,
        persisted,
        prediction,
        max_files=max_files,
        max_paths=max_paths,
    )
    if committed.get("status") == "block":
        return committed["output"], committed
    binding = committed["owner_result_binding"]
    receipt = committed["deterministic_commit_binding"]
    output = submit_stage(
        root,
        persisted,
        mode="block",
        apply=True,
        max_files=max_files,
        max_paths=max_paths,
        owner_result_ref=str(binding["ref"]),
        owner_result_sha256=str(binding["sha256"]),
        deterministic_commit_ref=str(receipt["ref"]),
        deterministic_commit_sha256=str(receipt["sha256"]),
    )
    if (
        output.get("status") == "block"
        or output.get("result_artifact_sha256")
        != committed.get("result_sha256")
    ):
        raise RuntimeError(
            "committed deterministic result differs from validated prediction"
        )
    return output, committed


def apply_prepared_deterministic(
    root: Path,
    preparation: dict[str, Any],
    *,
    operation: str,
    max_files: int,
    max_paths: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Preview without creating a lock; commit only after an exclusive recheck."""

    cycle_id = str(preparation["cycle_id"])
    require_cycle_mutation_contract(
        read_initialization_metadata(root, cycle_id),
        operation,
    )
    with ledger_lock(root, cycle_id, exclusive=False):
        _prediction, preview = _predict_and_preflight(
            root,
            preparation,
            max_files=max_files,
            max_paths=max_paths,
        )
    if preview["status"] == "block":
        return preview.get("output") or preview, None
    with ledger_lock(root, cycle_id, exclusive=True):
        require_cycle_mutation_contract(
            read_initialization_metadata(root, cycle_id),
            operation,
        )
        prediction, preflight = _predict_and_preflight(
            root,
            preparation,
            max_files=max_files,
            max_paths=max_paths,
        )
        if preflight["status"] == "block":
            return preflight.get("output") or preflight, None
        return _commit_preflighted(
            root,
            preparation,
            prediction,
            preflight,
            max_files=max_files,
            max_paths=max_paths,
        )


__all__ = ["apply_prepared_deterministic"]
