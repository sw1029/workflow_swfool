"""Closed stage-facade identity helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


PREPARATION_KIND = "orchestrate_stage_preparation"
PREPARATION_SCHEMA_VERSION = 1


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def state_fingerprint(
    model_context: dict[str, Any],
    dependency_roles: tuple[str, ...] | list[str] = ("core", "git", "diagnostics"),
) -> str:
    git = model_context.get("git") if isinstance(model_context.get("git"), dict) else {}
    diagnostics = (
        model_context.get("diagnostic_artifacts")
        if isinstance(model_context.get("diagnostic_artifacts"), dict)
        else {}
    )
    roles = frozenset(str(item) for item in dependency_roles)
    if "core" not in roles or not roles <= {"core", "git", "diagnostics"}:
        raise ValueError("invalid stage fingerprint dependency roles")
    material: dict[str, Any] = {
        "task": model_context.get("task"),
        "goal_truth": model_context.get("goal_truth"),
        "advice": model_context.get("advice"),
        "cycle": model_context.get("cycle"),
        "selection_publication": model_context.get("selection_publication"),
    }
    if "git" in roles:
        material["git"] = {
            "head": git.get("head"),
            "changed_path_set_sha256": (git.get("changed_paths") or {}).get(
                "set_sha256"
            )
            if isinstance(git.get("changed_paths"), dict)
            else None,
        }
    if "diagnostics" in roles:
        material["diagnostic_set_sha256"] = diagnostics.get("set_sha256")
    return canonical_sha256(material)


def preparation_identity(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "schema_version",
            "artifact_kind",
            "cycle_id",
            "target",
            "workflow_mode",
            "state_fingerprint",
            "fingerprint_roles",
            "model_packet_sha256",
            "derived_values",
            "result_contract",
        )
    }


def trusted_preparation_material(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity": preparation_identity(value),
        "model_packet": value.get("model_packet"),
        "derived_values": value.get("derived_values"),
        "result_contract": value.get("result_contract"),
        "fingerprint_roles": value.get("fingerprint_roles"),
    }


def preparation_binding_sha256(value: dict[str, Any]) -> str:
    return canonical_sha256(trusted_preparation_material(value))


def require_expected_preparation(
    supplied: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    if trusted_preparation_material(supplied) != trusted_preparation_material(expected):
        raise ValueError(
            "preparation_tampered: supplied preparation is not current compiler output"
        )
    return expected


def stale_preparation_result(
    preparation: dict[str, Any], actual_fingerprint: str
) -> dict[str, Any]:
    return {
        "status": "block",
        "stop_reason": "stale_preparation",
        "preparation_id": preparation["preparation_id"],
        "expected_state_fingerprint": preparation["state_fingerprint"],
        "actual_state_fingerprint": actual_fingerprint,
        "applied": False,
    }


def validate_preparation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("stage preparation must be a JSON object")
    if value.get("schema_version") != PREPARATION_SCHEMA_VERSION:
        raise ValueError("unsupported stage preparation schema_version")
    if value.get("artifact_kind") != PREPARATION_KIND:
        raise ValueError("stage preparation has an invalid artifact_kind")
    identity = preparation_identity(value)
    expected = "stageprep-" + canonical_sha256(identity)[:32]
    if value.get("preparation_id") != expected:
        raise ValueError("stage preparation identity does not match its content")
    model_context = value.get("model_context")
    roles = value.get("fingerprint_roles")
    if not isinstance(roles, list):
        raise ValueError("stage preparation fingerprint_roles must be a list")
    if not isinstance(model_context, dict) or state_fingerprint(
        model_context, roles
    ) != value.get("state_fingerprint"):
        raise ValueError("stage preparation model_context binding is invalid")
    if canonical_sha256(value.get("model_packet")) != value.get("model_packet_sha256"):
        raise ValueError("stage preparation model_packet binding is invalid")
    return value


def leaf_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(leaf_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(leaf_count(item) for item in value)
    return 1


__all__ = [
    "PREPARATION_KIND",
    "PREPARATION_SCHEMA_VERSION",
    "canonical_bytes",
    "canonical_sha256",
    "leaf_count",
    "preparation_binding_sha256",
    "preparation_identity",
    "require_expected_preparation",
    "stale_preparation_result",
    "state_fingerprint",
    "trusted_preparation_material",
    "validate_preparation",
]
