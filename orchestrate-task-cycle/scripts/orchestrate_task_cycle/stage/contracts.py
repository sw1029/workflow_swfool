"""Closed stage-facade identity helpers."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .v2_specs import EXECUTOR_KINDS


PREPARATION_KIND = "orchestrate_stage_preparation"
PREPARATION_SCHEMA_VERSION = 1
PREPARATION_SCHEMA_VERSION_V2 = 2
SUPPORTED_PREPARATION_SCHEMA_VERSIONS = frozenset(
    {PREPARATION_SCHEMA_VERSION, PREPARATION_SCHEMA_VERSION_V2}
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


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
    if value.get("schema_version") == PREPARATION_SCHEMA_VERSION_V2:
        return {
            key: value.get(key)
            for key in (
                "schema_version",
                "artifact_kind",
                "cycle_id",
                "target",
                "workflow_mode",
                "executor_kind",
                "model_call_required",
                "state_fingerprint",
                "fingerprint_roles",
                "context_binding",
                "work_order_binding",
                "derived_values",
                "result_contract",
                "next_action",
            )
        }
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
    if value.get("schema_version") == PREPARATION_SCHEMA_VERSION_V2:
        return {"identity": preparation_identity(value)}
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
    version = value.get("schema_version")
    if version not in SUPPORTED_PREPARATION_SCHEMA_VERSIONS:
        raise ValueError("unsupported stage preparation schema_version")
    if value.get("artifact_kind") != PREPARATION_KIND:
        raise ValueError("stage preparation has an invalid artifact_kind")
    identity = preparation_identity(value)
    expected = "stageprep-" + canonical_sha256(identity)[:32]
    if value.get("preparation_id") != expected:
        raise ValueError("stage preparation identity does not match its content")
    roles = value.get("fingerprint_roles")
    if not isinstance(roles, list):
        raise ValueError("stage preparation fingerprint_roles must be a list")
    if version == PREPARATION_SCHEMA_VERSION_V2:
        _validate_v2_preparation(value)
        return value
    model_context = value.get("model_context")
    if not isinstance(model_context, dict) or state_fingerprint(
        model_context, roles
    ) != value.get("state_fingerprint"):
        raise ValueError("stage preparation model_context binding is invalid")
    if canonical_sha256(value.get("model_packet")) != value.get("model_packet_sha256"):
        raise ValueError("stage preparation model_packet binding is invalid")
    return value


def _validate_binding(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"stage preparation {label} must be an object")
    if value.get("artifact_type") != label.removesuffix("_binding"):
        raise ValueError(f"stage preparation {label} has an invalid artifact_type")
    if not isinstance(value.get("ref"), str) or not value.get("ref"):
        raise ValueError(f"stage preparation {label} requires ref")
    if not SHA256_PATTERN.fullmatch(str(value.get("sha256") or "")):
        raise ValueError(f"stage preparation {label} requires raw sha256")
    size = value.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError(f"stage preparation {label} requires positive size_bytes")


def _validate_v2_preparation(value: dict[str, Any]) -> None:
    if value.get("executor_kind") not in EXECUTOR_KINDS - {"system"}:
        raise ValueError("stage preparation has an invalid executor_kind")
    if "model_context" in value or "model_packet" in value:
        raise ValueError("v2 stage preparation must not embed context or packet bodies")
    _validate_binding(value.get("context_binding"), "context_binding")
    _validate_binding(value.get("work_order_binding"), "work_order_binding")
    contract = value.get("result_contract")
    if not isinstance(contract, dict):
        raise ValueError("v2 stage preparation result_contract must be an object")
    semantic = contract.get("semantic_fields")
    if not isinstance(semantic, list):
        raise ValueError("v2 result_contract semantic_fields must be a list")
    if value.get("model_call_required") is not bool(semantic):
        raise ValueError("v2 model_call_required does not match semantic field count")


def leaf_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(leaf_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(leaf_count(item) for item in value)
    return 1


__all__ = [
    "PREPARATION_KIND",
    "PREPARATION_SCHEMA_VERSION",
    "PREPARATION_SCHEMA_VERSION_V2",
    "SUPPORTED_PREPARATION_SCHEMA_VERSIONS",
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
