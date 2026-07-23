"""Compile many operations from one producer-owned semantic context."""

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
    write_immutable_json,
)
from .operation_compiler import (
    SCOPE_KEYS,
    SUBJECT_SEED_KEYS,
    compile_operation,
)
from .operation_publication import publish_compilation
from .semantic_context import load_shared_semantic_context


OPERATION_SEED_KEYS = {
    "skill_id",
    "operation_id",
    "subject",
    "scope",
    "cardinality_requested",
    "use_budget_requested",
    "reservation_units",
    "classification",
    "composition_receipt",
}
BATCH_KEYS = {
    "schema_version",
    "artifact_kind",
    "compiled_at",
    "semantic_context",
    "operation_set",
    "operation_compilations",
    "operation_count",
    "field_provenance",
    "batch_fingerprint",
}
OPERATION_SET_KEYS = {
    "schema_version",
    "artifact_kind",
    "operations",
    "operation_count",
    "field_provenance",
    "operation_set_fingerprint",
}
OPERATION_SET_ROOT = Path(".task/authorization/operation_sets/sha256")
OPERATION_BATCH_ROOT = Path(".task/authorization/operation_batches/sha256")
MAX_OPERATION_SET_COUNT = 128
MAX_OPERATION_SET_BYTES = 256 * 1024
MAX_OPERATION_BATCH_BYTES = 2 * 1024 * 1024

OPERATION_SET_PROVENANCE = {
    "caller_semantic": [
        "operation identities",
        "subjects and revisions",
        "scope",
        "independent decision axes",
    ],
    "compiler_derived": [
        "schema markers",
        "canonical ordering",
        "operation-set fingerprint",
        "CAS path",
    ],
    "authority_effect": "none",
}
BATCH_PROVENANCE = {
    "caller_semantic": [
        "operation identities",
        "subjects and revisions",
        "scope",
        "independent decision axes",
    ],
    "shared_semantic": [
        "actor rank",
        "request status axes",
        "session ceiling",
        "goal autonomy envelope",
    ],
    "compiler_derived": [
        "manifest classifications",
        "subject and evidence hashes",
        "request IDs and digests",
        "compilation bindings",
        "batch fingerprint and CAS path",
    ],
    "authority_effect": "none",
}


def _closed_seed(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit(f"operation batch seed[{index}] must be an object.")
    extra = sorted(set(value) - OPERATION_SEED_KEYS)
    required = {"skill_id", "operation_id", "subject", "scope"}
    missing = sorted(required - set(value))
    if extra or missing:
        raise SystemExit(
            f"operation batch seed[{index}] has unknown={extra} missing={missing}."
        )
    subject = value["subject"]
    if (
        not isinstance(subject, dict)
        or not {"ref", "revision"}.issubset(subject)
        or set(subject) - SUBJECT_SEED_KEYS
    ):
        raise SystemExit(
            f"operation batch seed[{index}].subject is not a closed semantic subject."
        )
    scope = value["scope"]
    if not isinstance(scope, dict) or set(scope) - SCOPE_KEYS:
        raise SystemExit(
            f"operation batch seed[{index}].scope is not a closed semantic scope."
        )
    classification = value.get("classification", {})
    if not isinstance(classification, dict):
        raise SystemExit(
            f"operation batch seed[{index}].classification must be an object."
        )
    normalized_classification = copy.deepcopy(classification)
    if "required_capabilities" in normalized_classification:
        capabilities = normalized_classification["required_capabilities"]
        if not isinstance(capabilities, list):
            raise SystemExit(
                f"operation batch seed[{index}] classification capabilities "
                "must be a list."
            )
        normalized = sorted(set(str(item) for item in capabilities))
        if len(normalized) != len(capabilities):
            raise SystemExit(
                f"operation batch seed[{index}] classification capabilities "
                "must be unique."
            )
        normalized_classification["required_capabilities"] = normalized
    return {
        "skill_id": copy.deepcopy(value["skill_id"]),
        "operation_id": copy.deepcopy(value["operation_id"]),
        "subject": copy.deepcopy(subject),
        "scope": {key: copy.deepcopy(scope.get(key)) for key in sorted(SCOPE_KEYS)},
        "cardinality_requested": copy.deepcopy(
            value.get("cardinality_requested", "single_use")
        ),
        "use_budget_requested": copy.deepcopy(value.get("use_budget_requested", 1)),
        "reservation_units": copy.deepcopy(value.get("reservation_units", 1)),
        "classification": normalized_classification,
        "composition_receipt": copy.deepcopy(value.get("composition_receipt")),
    }


def compile_operation_set(operation_seeds: Any) -> dict[str, Any]:
    if not isinstance(operation_seeds, list) or not operation_seeds:
        raise SystemExit("operation set must contain at least one semantic seed.")
    if len(operation_seeds) > MAX_OPERATION_SET_COUNT:
        raise SystemExit(
            f"operation set exceeds the {MAX_OPERATION_SET_COUNT}-operation limit."
        )
    supplied = [
        _closed_seed(value, index) for index, value in enumerate(operation_seeds)
    ]
    keyed = [(canonical_bytes(value), value) for value in supplied]
    if len({key for key, _value in keyed}) != len(keyed):
        raise SystemExit("operation set contains a duplicate semantic operation.")
    operations = [
        value for _key, value in sorted(keyed, key=lambda item: item[0])
    ]
    if len(canonical_bytes(operations)) > MAX_OPERATION_SET_BYTES:
        raise SystemExit(
            f"operation set exceeds the {MAX_OPERATION_SET_BYTES}-byte limit."
        )
    body = {
        "schema_version": 1,
        "artifact_kind": "authority_operation_set",
        "operations": operations,
        "operation_count": len(operations),
        "field_provenance": copy.deepcopy(OPERATION_SET_PROVENANCE),
    }
    return {**body, "operation_set_fingerprint": object_sha256(body)}


def validate_operation_set(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != OPERATION_SET_KEYS:
        raise SystemExit("Authority operation set is not a closed typed object.")
    if (
        value["schema_version"] != 1
        or value["artifact_kind"] != "authority_operation_set"
    ):
        raise SystemExit("Unsupported authority operation-set contract.")
    operations = value["operations"]
    expected = compile_operation_set(operations)
    if value != expected or value["operation_count"] != len(operations):
        raise SystemExit("Authority operation set differs from compiler rendering.")
    return expected


def publish_operation_set(root: Path, operation_seeds: Any) -> dict[str, Any]:
    root = root.resolve()
    operation_set = compile_operation_set(operation_seeds)
    fingerprint = operation_set["operation_set_fingerprint"]
    target = root / OPERATION_SET_ROOT / f"{fingerprint}.json"
    digest = write_immutable_json(target, operation_set, "authority operation set")
    return {
        "status": "published",
        "operation_set": {
            "ref": target.relative_to(root).as_posix(),
            "sha256": digest,
        },
        "operation_set_fingerprint": fingerprint,
        "operation_count": operation_set["operation_count"],
        "model_authored_mechanical_bytes": 0,
    }


def load_operation_set(
    root: Path, binding: dict[str, str]
) -> tuple[dict[str, str], dict[str, Any]]:
    root = root.resolve()
    path = verify_binding(root, binding, "operation set")
    try:
        path.relative_to(root / OPERATION_SET_ROOT)
    except ValueError as exc:
        raise SystemExit("Operation set is outside the producer-owned CAS.") from exc
    operation_set = validate_operation_set(read_object(path, "operation set"))
    if path.name != f"{operation_set['operation_set_fingerprint']}.json":
        raise SystemExit("Operation-set CAS path does not match its fingerprint.")
    normalized = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }
    if normalized != binding:
        raise SystemExit("Operation-set binding is not canonical.")
    return normalized, operation_set


def compile_operation_batch(
    root: Path,
    semantic_context_binding: dict[str, str],
    operation_set_binding: dict[str, str],
    *,
    compiled_at: str,
    skills_root: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compile a closed batch; callers provide semantics, not repeated contexts."""

    root = root.resolve()
    context_binding, shared = load_shared_semantic_context(
        root, semantic_context_binding
    )
    normalized_operation_set, operation_set = load_operation_set(
        root, operation_set_binding
    )
    operation_seeds = operation_set["operations"]
    at = normalized_time(compiled_at, "operation batch compiled_at")
    compiled: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str]] = set()
    evaluation = shared["evaluation_context"]
    shared_request = shared["request_context"]
    request_seed_context = {
        "external_input_status": shared_request["external_input_status"],
        "goal_truth_status": shared_request["goal_truth_status"],
        "risk_acceptance_status": shared_request["risk_acceptance_status"],
        "design_selection_status": shared_request["design_selection_status"],
        **{
            f"{field}_ref": shared_request[field]["ref"]
            for field in (
                "external_input_evidence",
                "risk_acceptance_evidence",
                "design_selection_evidence",
            )
            if shared_request[field] is not None
        },
    }
    for index, raw in enumerate(operation_seeds):
        seed = _closed_seed(raw, index)
        scope = seed.get("scope")
        if not isinstance(scope, dict):
            raise SystemExit(f"operation batch seed[{index}].scope must be an object.")
        supplied_cycle = scope.get("cycle_id")
        if supplied_cycle not in {None, shared["cycle_id"]}:
            raise SystemExit(
                f"operation batch seed[{index}] conflicts with the shared cycle."
            )
        seed["scope"] = {**scope, "cycle_id": shared["cycle_id"]}
        supplied_task = scope.get("task_id")
        if supplied_task not in {None, shared["task_id"]}:
            raise SystemExit(
                f"operation batch seed[{index}] conflicts with the initialized task."
            )
        seed["scope"]["task_id"] = shared["task_id"]
        seed.update(
            {
                "actor_rank": shared["actor_rank"],
                "context": request_seed_context,
                "session_ceiling": evaluation["session_ceiling"],
                "goal_autonomy_envelope": {
                    **evaluation["goal_autonomy_envelope"],
                    "source_ref": evaluation["goal_autonomy_envelope"][
                        "source_binding"
                    ]["ref"],
                },
            }
        )
        seed["goal_autonomy_envelope"].pop("source_binding")
        value = compile_operation(
            root, seed, compiled_at=at, skills_root=skills_root
        )
        identity = (
            value["request"]["skill_id"]
            + ":"
            + value["request"]["skill_version"]
            + ":"
            + value["request"]["operation_id"]
            + ":"
            + value["request"]["operation_version"],
            value["request"]["subject"]["digest"],
            value["request"]["idempotency_key"],
        )
        if identity in identities:
            raise SystemExit("operation batch contains a duplicate compiled operation.")
        identities.add(identity)
        compiled.append(value)
    rows = [
        {
            "compilation": publish_compilation(root, value),
            "request_sha256": value["request_sha256"],
            "operation": {
                key: value["request"][key]
                for key in (
                    "skill_id",
                    "skill_version",
                    "operation_id",
                    "operation_version",
                )
            },
            "subject": value["request"]["subject"],
        }
        for value in compiled
    ]
    body = {
        "schema_version": 1,
        "artifact_kind": "authority_operation_batch",
        "compiled_at": at,
        "semantic_context": context_binding,
        "operation_set": normalized_operation_set,
        "operation_compilations": rows,
        "operation_count": len(rows),
        "field_provenance": copy.deepcopy(BATCH_PROVENANCE),
    }
    batch = {**body, "batch_fingerprint": object_sha256(body)}
    if len(canonical_bytes(batch)) > MAX_OPERATION_BATCH_BYTES:
        raise SystemExit(
            f"operation batch exceeds the {MAX_OPERATION_BATCH_BYTES}-byte limit."
        )
    return batch, compiled


def publish_operation_batch(
    root: Path,
    semantic_context_binding: dict[str, str],
    operation_set_binding: dict[str, str],
    *,
    compiled_at: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    batch, _compiled = compile_operation_batch(
        root,
        semantic_context_binding,
        operation_set_binding,
        compiled_at=compiled_at,
        skills_root=skills_root,
    )
    fingerprint = batch["batch_fingerprint"]
    target = root / OPERATION_BATCH_ROOT / f"{fingerprint}.json"
    digest = write_immutable_json(target, batch, "authority operation batch")
    return {
        "status": "published",
        "operation_batch": {
            "ref": target.relative_to(root).as_posix(),
            "sha256": digest,
        },
        "batch_fingerprint": fingerprint,
        "operation_count": batch["operation_count"],
        "model_authored_mechanical_bytes": 0,
    }


__all__ = (
    "OPERATION_BATCH_ROOT",
    "OPERATION_SET_ROOT",
    "MAX_OPERATION_BATCH_BYTES",
    "MAX_OPERATION_SET_BYTES",
    "MAX_OPERATION_SET_COUNT",
    "compile_operation_batch",
    "compile_operation_set",
    "load_operation_set",
    "publish_operation_batch",
    "publish_operation_set",
    "validate_operation_set",
)
