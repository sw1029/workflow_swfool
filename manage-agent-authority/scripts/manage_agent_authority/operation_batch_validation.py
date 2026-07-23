"""Validate producer-owned authority operation batches."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .artifact_store import verify_binding
from .canonical import (
    canonical_bytes,
    normalized_time,
    object_sha256,
    read_object,
    sha256_file,
)
from .operation_batch_compilation import (
    BATCH_KEYS,
    BATCH_PROVENANCE,
    MAX_OPERATION_BATCH_BYTES,
    OPERATION_BATCH_ROOT,
    _closed_seed,
    load_operation_set,
)
from .operation_compiler import compile_operation, validate_compilation
from .operation_publication import COMPILATION_ROOT
from .semantic_context import load_shared_semantic_context


def _load_row(
    root: Path, row: Any, index: int
) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) != {
        "compilation",
        "request_sha256",
        "operation",
        "subject",
    }:
        raise SystemExit(f"Authority operation batch row[{index}] is not closed.")
    path = verify_binding(root, row["compilation"], f"batch compilation[{index}]")
    compilation = validate_compilation(
        read_object(path, f"batch compilation[{index}]")
    )
    try:
        path.relative_to(root / COMPILATION_ROOT)
    except ValueError as exc:
        raise SystemExit(
            f"Batch compilation[{index}] is outside its producer store."
        ) from exc
    expected_name = (
        "operation_compilation-"
        + compilation["compilation_fingerprint"]
        + ".json"
    )
    if path.name != expected_name:
        raise SystemExit(
            f"Batch compilation[{index}] path does not match its fingerprint."
        )
    expected_operation = {
        key: compilation["request"][key]
        for key in (
            "skill_id",
            "skill_version",
            "operation_id",
            "operation_version",
        )
    }
    if (
        row["request_sha256"] != compilation["request_sha256"]
        or row["operation"] != expected_operation
        or row["subject"] != compilation["request"]["subject"]
    ):
        raise SystemExit(f"Authority operation batch row[{index}] differs.")
    return compilation


def _assert_row_matches_seed(
    compilation: dict[str, Any],
    seed: dict[str, Any],
    shared: dict[str, Any],
    index: int,
) -> None:
    request = compilation["request"]
    scope = seed["scope"]
    mismatched = (
        request["skill_id"] != seed["skill_id"]
        or request["operation_id"] != seed["operation_id"]
        or request["subject"]["ref"] != seed["subject"]["ref"]
        or request["subject"]["revision"] != seed["subject"]["revision"]
        or (
            seed["subject"].get("kind") is not None
            and request["subject"]["kind"] != seed["subject"]["kind"]
        )
        or request["cycle_id"] != shared["cycle_id"]
        or request["task_id"] != shared["task_id"]
        or request["pack_id"] != scope.get("pack_id")
        or request["actor_rank"] != shared["actor_rank"]
        or request["context"] != shared["request_context"]
        or compilation["evaluation_context"] != shared["evaluation_context"]
        or request["intent_type"] != "grant_authority"
        or request["cardinality_requested"]
        != seed.get("cardinality_requested", "single_use")
        or request["use_budget_requested"] != seed.get("use_budget_requested", 1)
        or request["reservation_units"] != seed.get("reservation_units", 1)
        or request["composition_receipt"] != seed.get("composition_receipt")
    )
    if mismatched:
        raise SystemExit(
            f"Authority operation batch row[{index}] differs from its operation set."
        )


def _reconstructed_seed(
    seed: dict[str, Any], shared: dict[str, Any], index: int
) -> dict[str, Any]:
    reconstructed = _closed_seed(seed, index)
    reconstructed["scope"] = {
        **reconstructed["scope"],
        "cycle_id": shared["cycle_id"],
        "task_id": shared["task_id"],
    }
    request_context = shared["request_context"]
    context = {
        "external_input_status": request_context["external_input_status"],
        "goal_truth_status": request_context["goal_truth_status"],
        "risk_acceptance_status": request_context["risk_acceptance_status"],
        "design_selection_status": request_context["design_selection_status"],
        **{
            f"{field}_ref": request_context[field]["ref"]
            for field in (
                "external_input_evidence",
                "risk_acceptance_evidence",
                "design_selection_evidence",
            )
            if request_context[field] is not None
        },
    }
    envelope = {
        **shared["evaluation_context"]["goal_autonomy_envelope"],
        "source_ref": shared["evaluation_context"]["goal_autonomy_envelope"][
            "source_binding"
        ]["ref"],
    }
    envelope.pop("source_binding")
    reconstructed.update(
        {
            "actor_rank": shared["actor_rank"],
            "context": context,
            "session_ceiling": shared["evaluation_context"]["session_ceiling"],
            "goal_autonomy_envelope": envelope,
        }
    )
    return reconstructed


def _validate_row(
    root: Path,
    row: Any,
    seed: dict[str, Any],
    shared: dict[str, Any],
    index: int,
    at: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    compilation = _load_row(root, row, index)
    _assert_row_matches_seed(compilation, seed, shared, index)
    expected = compile_operation(
        root,
        _reconstructed_seed(seed, shared, index),
        compiled_at=at,
        skills_root=skills_root,
    )
    if compilation != expected:
        raise SystemExit(
            f"Authority operation batch row[{index}] is not the exact "
            "compiler rendering of its operation-set seed."
        )
    return compilation


def validate_operation_batch(
    root: Path,
    value: Any,
    *,
    skills_root: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(value, dict) or set(value) != BATCH_KEYS:
        raise SystemExit("Authority operation batch is not a closed typed object.")
    if (
        value["schema_version"] != 1
        or value["artifact_kind"] != "authority_operation_batch"
    ):
        raise SystemExit("Unsupported authority operation batch contract.")
    root = root.resolve()
    context_binding, shared = load_shared_semantic_context(
        root, value["semantic_context"]
    )
    operation_set_binding, operation_set = load_operation_set(
        root, value["operation_set"]
    )
    rows = value["operation_compilations"]
    if (
        not isinstance(rows, list)
        or not rows
        or value["operation_count"] != len(rows)
        or value["operation_count"] != operation_set["operation_count"]
    ):
        raise SystemExit("Authority operation batch count is invalid.")
    at = normalized_time(value["compiled_at"], "operation batch compiled_at")
    if at != value["compiled_at"]:
        raise SystemExit("Authority operation batch compiled_at is not canonical.")
    if value["field_provenance"] != BATCH_PROVENANCE:
        raise SystemExit(
            "Authority operation batch provenance differs from compiler output."
        )
    compilations = [
        _validate_row(
            root,
            row,
            operation_set["operations"][index],
            shared,
            index,
            at,
            skills_root,
        )
        for index, row in enumerate(rows)
    ]
    body = {
        "schema_version": 1,
        "artifact_kind": "authority_operation_batch",
        "compiled_at": at,
        "semantic_context": context_binding,
        "operation_set": operation_set_binding,
        "operation_compilations": copy.deepcopy(rows),
        "operation_count": len(rows),
        "field_provenance": copy.deepcopy(BATCH_PROVENANCE),
    }
    if value["batch_fingerprint"] != object_sha256(body):
        raise SystemExit("Authority operation batch fingerprint mismatch.")
    normalized = {**body, "batch_fingerprint": value["batch_fingerprint"]}
    if value != normalized:
        raise SystemExit("Authority operation batch differs from compiler rendering.")
    if len(canonical_bytes(normalized)) > MAX_OPERATION_BATCH_BYTES:
        raise SystemExit(
            f"operation batch exceeds the {MAX_OPERATION_BATCH_BYTES}-byte limit."
        )
    return normalized, compilations


def load_operation_batch(
    root: Path,
    binding: dict[str, str],
    *,
    skills_root: Path | None = None,
) -> tuple[dict[str, str], dict[str, Any], list[dict[str, Any]]]:
    root = root.resolve()
    path = verify_binding(root, binding, "operation batch")
    try:
        path.relative_to(root / OPERATION_BATCH_ROOT)
    except ValueError as exc:
        raise SystemExit("Operation batch is outside the producer-owned CAS.") from exc
    batch, compilations = validate_operation_batch(
        root, read_object(path, "operation batch"), skills_root=skills_root
    )
    if path.name != f"{batch['batch_fingerprint']}.json":
        raise SystemExit("Operation batch CAS path does not match its fingerprint.")
    normalized = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }
    if normalized != binding:
        raise SystemExit("Operation batch binding is not canonical.")
    return normalized, batch, compilations


__all__ = ("load_operation_batch", "validate_operation_batch")
