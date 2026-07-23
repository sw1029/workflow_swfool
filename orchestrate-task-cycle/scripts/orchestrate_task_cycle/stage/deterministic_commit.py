"""Hard-gated durable deterministic commit effects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..dashboard.io import atomic_write
from ..ledger.support import read_initialization_metadata
from ..ledger.workflow_contract import require_cycle_mutation_contract
from .artifact_store import load_compiler_artifact, write_stage_input
from .contracts import canonical_bytes
from .deterministic_receipt import _publish_deterministic_commit_receipt
from .executor_registry import executor_spec


def commit_deterministic_gated(
    root: Path,
    preparation: dict[str, Any],
    prediction: dict[str, Any],
    *,
    max_files: int = 12,
    max_paths: int = 40,
) -> dict[str, Any]:
    """Re-run hardcoded gates, then commit their exact renderer projection."""

    from .deterministic_dispatch import predict_deterministic
    from .v2_service import _preflight_deterministic_submission

    cycle_id, target = (
        str(preparation["cycle_id"]),
        str(preparation["target"]),
    )
    require_cycle_mutation_contract(
        read_initialization_metadata(root, cycle_id),
        "commit deterministic stage",
    )
    load_compiler_artifact(
        root,
        cycle_id,
        preparation["machine_input_binding"],
        "machine_input",
    )
    current = predict_deterministic(
        root,
        preparation,
        max_files=max_files,
        max_paths=max_paths,
    )
    compared = ("raw_owner_result", "effect_plan")
    if canonical_bytes(
        {key: current.get(key) for key in compared}
    ) != canonical_bytes(
        {key: prediction.get(key) for key in compared}
    ):
        raise ValueError("deterministic prediction changed before commit")
    preflight = _preflight_deterministic_submission(
        root,
        preparation,
        current,
        mode="block",
        max_files=max_files,
        max_paths=max_paths,
    )
    if preflight.get("status") == "block":
        return {
            "status": "block",
            "output": preflight.get("output") or preflight,
            "effect_committed": False,
            "model_call_count": 0,
            "model_visible_bytes": 0,
        }
    result_sha256 = str(preflight["result_sha256"])
    effect = current.get("effect_plan")
    if effect is not None:
        if (
            not isinstance(effect, dict)
            or effect.get("kind") != "write_text"
            or not isinstance(effect.get("content"), str)
        ):
            raise ValueError("deterministic effect plan is invalid")
        atomic_write(root / str(effect["ref"]), str(effect["content"]))
    rederived = predict_deterministic(
        root,
        preparation,
        max_files=max_files,
        max_paths=max_paths,
    )
    if canonical_bytes(
        {key: rederived.get(key) for key in compared}
    ) != canonical_bytes(
        {key: current.get(key) for key in compared}
    ):
        raise RuntimeError("deterministic result changed after effect commit")
    binding = write_stage_input(
        root,
        cycle_id,
        target,
        "owner_result",
        rederived["raw_owner_result"],
        preparation=preparation,
    )
    commit_binding = _publish_deterministic_commit_receipt(
        root,
        preparation,
        rederived,
        result_sha256,
        binding,
    )
    return {
        "executor_spec": executor_spec(target).projection(),
        "owner_result_binding": binding,
        "deterministic_commit_binding": commit_binding,
        "model_call_count": 0,
        "model_visible_bytes": 0,
        "owner_result_bytes": rederived["owner_result_bytes"],
        "freshness_status": "exact_precondition",
        "effect_committed": effect is not None,
        "result_sha256": result_sha256,
    }


__all__ = ["commit_deterministic_gated"]
