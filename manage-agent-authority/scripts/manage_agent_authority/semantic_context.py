"""Compile cycle-shared authority semantics into one immutable CAS artifact."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .artifact_store import verify_binding
from .canonical import (
    canonical_bytes,
    object_sha256,
    read_object,
    sha256_file,
    write_immutable_json,
)
from .contracts import (
    EXTERNAL_INPUT,
    GOAL_TRUTH,
    SEPARATE_DECISION_STATUS,
    SOURCE_RANKS,
)
from .evaluation_context import validate_evaluation_context, verify_request_evidence
from .operation_compiler import (
    ENVELOPE_SEED_KEYS,
    SESSION_SEED_KEYS,
    _binding,
    _closed,
    _exact_id,
    _request_context,
    _required,
)


MAX_SEMANTIC_CONTEXT_BYTES = 64 * 1024
SEMANTIC_KEYS = {
    "actor_rank",
    "request_context",
    "session_ceiling",
    "goal_autonomy_envelope",
}
ARTIFACT_KEYS = {
    "schema_version",
    "artifact_kind",
    "initialization",
    "cycle_id",
    "task_id",
    "actor_rank",
    "request_context",
    "evaluation_context",
    "field_provenance",
    "semantic_fingerprint",
}
SEMANTIC_CONTEXT_ROOT = Path(".task/authorization/semantic_contexts/sha256")


def compile_shared_semantic_context(
    root: Path,
    initialization_binding: dict[str, str],
    value: Any,
) -> dict[str, Any]:
    """Normalize caller-owned facts without deriving or widening their scope."""

    root = root.resolve()
    semantic = _closed(
        copy.deepcopy(value),
        SEMANTIC_KEYS,
        "semantic context",
    )
    _required(semantic, SEMANTIC_KEYS, "semantic context")
    initialization_path = verify_binding(
        root, initialization_binding, "cycle initialization"
    )
    initialization = read_object(initialization_path, "cycle initialization")
    cycle_id = _exact_id(
        initialization.get("cycle_id"), "cycle initialization cycle_id"
    )
    task_id = _exact_id(
        initialization.get("task_id"), "cycle initialization task_id"
    )
    expected_path = root / ".task/cycle" / cycle_id / "initialization.json"
    if initialization_path != expected_path:
        raise SystemExit(
            "Cycle initialization binding is outside its canonical cycle path."
        )
    normalized_initialization = {
        "ref": initialization_path.relative_to(root).as_posix(),
        "sha256": sha256_file(initialization_path),
    }
    if normalized_initialization != initialization_binding:
        raise SystemExit("Cycle initialization binding is not canonical.")
    actor_rank = str(semantic["actor_rank"])
    if actor_rank not in SOURCE_RANKS:
        raise SystemExit("semantic context actor_rank is invalid.")
    request_context = _request_context(root, semantic["request_context"])
    session = _closed(
        semantic["session_ceiling"], SESSION_SEED_KEYS, "session_ceiling"
    )
    envelope = _closed(
        semantic["goal_autonomy_envelope"],
        ENVELOPE_SEED_KEYS,
        "goal_autonomy_envelope",
    )
    _required(session, SESSION_SEED_KEYS, "session_ceiling")
    _required(envelope, ENVELOPE_SEED_KEYS, "goal_autonomy_envelope")
    evaluation = validate_evaluation_context(
        root,
        {
            "schema_version": 2,
            "context_kind": "authority_evaluation",
            "session_ceiling": {
                **copy.deepcopy(session),
                "evidence_id": _exact_id(
                    session["evidence_id"], "session_ceiling.evidence_id"
                ),
            },
            "goal_autonomy_envelope": {
                **{
                    key: copy.deepcopy(envelope[key])
                    for key in ENVELOPE_SEED_KEYS
                    if key != "source_ref"
                },
                "envelope_id": _exact_id(
                    envelope["envelope_id"],
                    "goal_autonomy_envelope.envelope_id",
                ),
                "source_binding": _binding(
                    root, envelope["source_ref"], "goal autonomy source"
                ),
            },
        },
    )
    body = {
        "schema_version": 1,
        "artifact_kind": "authority_cycle_semantic_context",
        "initialization": normalized_initialization,
        "cycle_id": cycle_id,
        "task_id": task_id,
        "actor_rank": actor_rank,
        "request_context": request_context,
        "evaluation_context": evaluation,
        "field_provenance": {
            "caller_semantic": [
                "actor_rank",
                "request_context status axes",
                "session ceiling",
                "goal autonomy envelope",
            ],
            "compiler_derived": [
                "schema markers",
                "cycle/task derivation from initialization",
                "evidence digests",
                "goal source digest",
                "canonical ordering",
                "semantic fingerprint",
                "CAS path",
            ],
            "authority_effect": "none",
        },
    }
    result = {**body, "semantic_fingerprint": object_sha256(body)}
    if len(canonical_bytes(result)) > MAX_SEMANTIC_CONTEXT_BYTES:
        raise SystemExit("Compiled semantic context exceeds the 64 KiB bound.")
    return result


def validate_shared_semantic_context(
    root: Path,
    value: Any,
) -> dict[str, Any]:
    context = _closed(
        copy.deepcopy(value), ARTIFACT_KEYS, "compiled semantic context"
    )
    _required(context, ARTIFACT_KEYS, "compiled semantic context")
    if (
        context["schema_version"] != 1
        or context["artifact_kind"] != "authority_cycle_semantic_context"
    ):
        raise SystemExit("Unsupported compiled semantic context contract.")
    initialization_path = verify_binding(
        root.resolve(), context["initialization"], "cycle initialization"
    )
    initialization = read_object(initialization_path, "cycle initialization")
    cycle_id = _exact_id(context["cycle_id"], "compiled semantic context cycle_id")
    task_id = _exact_id(context["task_id"], "compiled semantic context task_id")
    if (
        initialization.get("cycle_id") != cycle_id
        or initialization.get("task_id") != task_id
        or initialization_path
        != root.resolve() / ".task/cycle" / cycle_id / "initialization.json"
    ):
        raise SystemExit(
            "Compiled semantic context differs from cycle initialization."
        )
    normalized_initialization = {
        "ref": initialization_path.relative_to(root.resolve()).as_posix(),
        "sha256": sha256_file(initialization_path),
    }
    if context["initialization"] != normalized_initialization:
        raise SystemExit("Compiled cycle initialization binding is not canonical.")
    if context["actor_rank"] not in SOURCE_RANKS:
        raise SystemExit("Compiled semantic context actor_rank is invalid.")
    evaluation = validate_evaluation_context(root.resolve(), context["evaluation_context"])
    request = context["request_context"]
    if not isinstance(request, dict) or set(request) != {
        "external_input_status",
        "goal_truth_status",
        "risk_acceptance_status",
        "design_selection_status",
        "external_input_evidence",
        "risk_acceptance_evidence",
        "design_selection_evidence",
    }:
        raise SystemExit("Compiled request context is not closed.")
    if request["external_input_status"] not in EXTERNAL_INPUT:
        raise SystemExit("Compiled external-input status is invalid.")
    if request["goal_truth_status"] not in GOAL_TRUTH:
        raise SystemExit("Compiled goal-truth status is invalid.")
    if (
        request["risk_acceptance_status"] not in SEPARATE_DECISION_STATUS
        or request["design_selection_status"] not in SEPARATE_DECISION_STATUS
    ):
        raise SystemExit("Compiled separate-decision status is invalid.")
    evidence_rules = {
        "external_input_evidence": request["external_input_status"]
        in {"available", "missing_supplyable", "missing_unsupplyable"},
        "risk_acceptance_evidence": request["risk_acceptance_status"] == "resolved",
        "design_selection_evidence": request["design_selection_status"] == "resolved",
    }
    for field, required in evidence_rules.items():
        binding = request[field]
        if required != (binding is not None):
            raise SystemExit(f"Compiled {field} does not match its status.")
        if binding is not None and (
            not isinstance(binding, dict) or set(binding) != {"ref", "sha256"}
        ):
            raise SystemExit(f"Compiled {field} binding is not closed.")
    verify_request_evidence(root.resolve(), {"context": request})
    body = {
        key: copy.deepcopy(context[key])
        for key in ARTIFACT_KEYS
        if key != "semantic_fingerprint"
    }
    body["initialization"] = normalized_initialization
    body["evaluation_context"] = evaluation
    if context["semantic_fingerprint"] != object_sha256(body):
        raise SystemExit("Compiled semantic context fingerprint mismatch.")
    return {**body, "semantic_fingerprint": context["semantic_fingerprint"]}


def publish_shared_semantic_context(
    root: Path,
    initialization_binding: dict[str, str],
    semantic: Any,
) -> dict[str, Any]:
    root = root.resolve()
    context = compile_shared_semantic_context(
        root, initialization_binding, semantic
    )
    fingerprint = context["semantic_fingerprint"]
    target = root / SEMANTIC_CONTEXT_ROOT / f"{fingerprint}.json"
    digest = write_immutable_json(target, context, "authority semantic context")
    return {
        "status": "published",
        "semantic_context": {
            "ref": target.relative_to(root).as_posix(),
            "sha256": digest,
        },
        "semantic_fingerprint": fingerprint,
        "model_authored_mechanical_bytes": 0,
    }


def load_shared_semantic_context(
    root: Path,
    binding: dict[str, str],
) -> tuple[dict[str, str], dict[str, Any]]:
    root = root.resolve()
    path = verify_binding(root, binding, "semantic context")
    expected_root = root / SEMANTIC_CONTEXT_ROOT
    try:
        path.relative_to(expected_root)
    except ValueError as exc:
        raise SystemExit("Semantic context is outside the producer-owned CAS.") from exc
    value = validate_shared_semantic_context(
        root, read_object(path, "semantic context")
    )
    if path.name != f"{value['semantic_fingerprint']}.json":
        raise SystemExit("Semantic context CAS path does not match its fingerprint.")
    normalized = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }
    if normalized != binding:
        raise SystemExit("Semantic context binding is not canonical.")
    return normalized, value


__all__ = (
    "SEMANTIC_CONTEXT_ROOT",
    "compile_shared_semantic_context",
    "load_shared_semantic_context",
    "publish_shared_semantic_context",
    "validate_shared_semantic_context",
)
