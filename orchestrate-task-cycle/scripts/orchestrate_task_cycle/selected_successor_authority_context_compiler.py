"""Publish bounded authority contexts from explicit semantic inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selection_decision_store import normalize_binding
from .selection_publication_store import (
    _bounded_file_sha256,
    _bounded_payload,
    _canonical_json,
    _sha256_bytes,
    _successor_authority_evaluation_context_path,
    _successor_authority_request_context_path,
    _write_once,
)
from .selected_successor import load_selected_successor_bundle
from .selected_successor_authority_context import (
    MAX_CONTEXT_BYTES,
    normalize_evaluation_semantics,
    normalize_request_semantics,
)
from .selected_successor_execution_support import execution_rows


def _exact_id(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 128 or "*" in normalized:
        raise ValueError(f"{label} must be a bounded exact identifier")
    return normalized


def _operation_identity(value: dict[str, Any]) -> str:
    return ":".join(
        value[key]
        for key in (
            "skill_id",
            "skill_version",
            "operation_id",
            "operation_version",
        )
    )


def _requirements(
    bundle: dict[str, Any], skills_root: Path | None
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    from manage_agent_authority.operations import load_operation

    requirements: list[dict[str, Any]] = []
    manifests: dict[str, dict[str, str]] = {}
    for row in execution_rows(bundle):
        identity = row["operation"]
        operation, manifest = load_operation(
            identity["skill_id"],
            identity["skill_version"],
            identity["operation_id"],
            identity["operation_version"],
            skills_root=skills_root,
        )
        if operation is None or manifest is None:
            raise ValueError(
                f"Selected-successor {row['action']} operation manifest is unavailable"
            )
        if (
            operation["authorization_mechanism"] != "grant"
            or row["subject"]["kind"] not in operation["subject_kinds"]
        ):
            raise ValueError(
                f"Selected-successor {row['action']} is not grant-context compatible"
            )
        requirements.append(
            {
                "action": row["action"],
                "capabilities": operation["required_capabilities"],
                "risk": operation["risk_floor"],
                "mutation": operation["mutation_class"],
                "decision": operation["decision_class"],
                "subject": row["subject"]["digest"],
                "operation": _operation_identity(identity),
            }
        )
        manifests[row["action"]] = manifest
    return requirements, manifests


def _normalize_evaluation(
    root: Path,
    session_ceiling: Any,
    goal_autonomy_envelope: Any,
) -> dict[str, Any]:
    if not isinstance(session_ceiling, dict) or not isinstance(
        goal_autonomy_envelope, dict
    ):
        raise ValueError("Authority ceiling and envelope semantic inputs must be objects")
    session = dict(session_ceiling)
    envelope = dict(goal_autonomy_envelope)
    session["evidence_id"] = _exact_id(
        session.get("evidence_id"), "session evidence ID"
    )
    envelope["envelope_id"] = _exact_id(
        envelope.get("envelope_id"), "goal envelope ID"
    )
    envelope["source_binding"] = normalize_binding(
        envelope.get("source_binding"), "goal envelope source"
    )
    value = {
        "schema_version": 2,
        "context_kind": "authority_evaluation",
        "session_ceiling": session,
        "goal_autonomy_envelope": envelope,
    }
    normalized = normalize_evaluation_semantics(root, value)
    if any(
        not item or "*" in item
        for item in normalized["goal_autonomy_envelope"]["subjects"]
        + normalized["goal_autonomy_envelope"]["operations"]
    ):
        raise ValueError("Goal envelope subjects and operations must be exact")
    return normalized


def _validate_coverage(
    requirements: list[dict[str, Any]], evaluation: dict[str, Any]
) -> None:
    from manage_agent_authority.contracts import risk_value

    session = evaluation["session_ceiling"]
    envelope = evaluation["goal_autonomy_envelope"]
    session_capabilities = set(session["capabilities"])
    goal_capabilities = set(envelope["capabilities"])
    subjects = set(envelope["subjects"])
    operations = set(envelope["operations"])
    blockers: list[str] = []
    for item in requirements:
        capabilities = set(item["capabilities"])
        if not capabilities.issubset(session_capabilities):
            blockers.append(f"{item['action']}:session_capabilities")
        if not capabilities.issubset(goal_capabilities):
            blockers.append(f"{item['action']}:goal_capabilities")
        if risk_value(item["risk"]) > risk_value(session["risk_ceiling"]):
            blockers.append(f"{item['action']}:session_risk")
        if risk_value(item["risk"]) > risk_value(envelope["risk_ceiling"]):
            blockers.append(f"{item['action']}:goal_risk")
        if item["mutation"] not in session["mutation_classes"]:
            blockers.append(f"{item['action']}:session_mutation")
        if item["decision"] not in envelope["decision_classes"]:
            blockers.append(f"{item['action']}:goal_decision")
        if item["subject"] not in subjects:
            blockers.append(f"{item['action']}:goal_subject")
        if item["operation"] not in operations:
            blockers.append(f"{item['action']}:goal_operation")
    if blockers:
        raise ValueError(
            "Authority semantic ceiling does not cover the selected-successor bundle: "
            + ", ".join(blockers)
        )


def _request_payload(
    root: Path,
    bundle: dict[str, str],
    actor_rank: Any,
    request_context: Any,
) -> tuple[bytes, str]:
    from manage_agent_authority.contracts import SOURCE_RANKS

    rank = str(actor_rank or "")
    if rank not in SOURCE_RANKS:
        raise ValueError("Selected-successor actor_rank is invalid")
    semantics = normalize_request_semantics(root, request_context)
    body = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_authority_request_context",
        "bundle": bundle,
        "actor_rank": rank,
        "context": semantics,
    }
    content_sha256 = _sha256_bytes(_canonical_json(body))
    value = {**body, "context_content_sha256": content_sha256}
    return _bounded_payload(
        _canonical_json(value),
        MAX_CONTEXT_BYTES,
        "selected-successor authority request context",
    ), content_sha256


def _target_is_new(path: Path, payload: bytes, label: str) -> bool:
    if not path.exists() and not path.is_symlink():
        return True
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_CONTEXT_BYTES
        or _bounded_file_sha256(path, len(payload), label)
        != _sha256_bytes(payload)
    ):
        raise ValueError(f"{label} conflicts with immutable transaction evidence")
    return False


def prepare_selected_successor_authority_contexts(
    root: Path,
    *,
    bundle_binding: dict[str, str],
    actor_rank: str,
    request_context: dict[str, Any],
    session_ceiling: dict[str, Any],
    goal_autonomy_envelope: dict[str, Any],
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Validate semantic facts and publish request/evaluation CAS artifacts."""

    root = root.expanduser().resolve(strict=True)
    bundle_binding = normalize_binding(bundle_binding, "authority context bundle")
    bundle = load_selected_successor_bundle(root, bundle_binding)
    selected_skills = skills_root.resolve() if skills_root is not None else None
    requirements, manifests = _requirements(bundle, selected_skills)
    evaluation = _normalize_evaluation(
        root, session_ceiling, goal_autonomy_envelope
    )
    _validate_coverage(requirements, evaluation)
    request_payload, request_content_sha = _request_payload(
        root, bundle_binding, actor_rank, request_context
    )
    evaluation_payload = _bounded_payload(
        _canonical_json(evaluation),
        MAX_CONTEXT_BYTES,
        "selected-successor authority evaluation context",
    )
    evaluation_content_sha = _sha256_bytes(evaluation_payload)
    request_path = _successor_authority_request_context_path(
        root, request_content_sha
    )
    evaluation_path = _successor_authority_evaluation_context_path(
        root, evaluation_content_sha
    )
    request_created = _target_is_new(
        request_path, request_payload, "selected-successor authority request context"
    )
    evaluation_created = _target_is_new(
        evaluation_path,
        evaluation_payload,
        "selected-successor authority evaluation context",
    )
    request_sha = _write_once(
        request_path, request_payload, "selected-successor authority request context"
    )
    evaluation_sha = _write_once(
        evaluation_path,
        evaluation_payload,
        "selected-successor authority evaluation context",
    )
    mutation = request_created or evaluation_created
    return {
        "result_kind": "selected_successor_authority_context_preparation_result",
        "schema_version": 1,
        "status": "prepared",
        "bundle": bundle_binding,
        "request_context": {
            "ref": request_path.relative_to(root).as_posix(),
            "sha256": request_sha,
        },
        "evaluation_context": {
            "ref": evaluation_path.relative_to(root).as_posix(),
            "sha256": evaluation_sha,
        },
        "operation_manifests": manifests,
        "authority_effects_applied": False,
        "idempotent_replay": not mutation,
        "mutation_performed": mutation,
        "model_authored_mechanical_bytes": 0,
    }


__all__ = ("prepare_selected_successor_authority_contexts",)
