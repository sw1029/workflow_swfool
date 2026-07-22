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
PREPARATION_SCHEMA_VERSION_V3 = 3
SUPPORTED_PREPARATION_SCHEMA_VERSIONS = frozenset(
    {
        PREPARATION_SCHEMA_VERSION,
        PREPARATION_SCHEMA_VERSION_V2,
        PREPARATION_SCHEMA_VERSION_V3,
    }
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

_V1_PREPARATION_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_kind",
        "cycle_id",
        "target",
        "workflow_mode",
        "state_fingerprint",
        "fingerprint_roles",
        "model_context",
        "model_packet",
        "model_packet_sha256",
        "derived_values",
        "result_contract",
        "next_action",
        "preparation_id",
        "compiler_metrics",
    }
)
_V2_V3_COMMON_PREPARATION_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_kind",
        "cycle_id",
        "target",
        "workflow_mode",
        "executor_kind",
        "model_call_required",
        "executor_spec",
        "state_fingerprint",
        "fingerprint_roles",
        "derived_values",
        "result_contract",
        "next_action",
        "compiler_metrics",
        "preparation_id",
    }
)
_CONTEXT_PREPARATION_FIELDS = frozenset(
    {"context_binding", "work_order_binding"}
)
_MACHINE_PREPARATION_FIELDS = frozenset({"machine_input_binding"})
_V3_PRECONDITION_FIELDS = frozenset(
    {"precondition_fingerprints", "allowed_post_effect_selectors"}
)
_DYNAMIC_COMPILER_METRIC_FIELDS = frozenset(
    {"cas_newly_written_bytes", "cas_reused_bytes", "files_written_count"}
)
_BINDING_FIELDS = frozenset({"artifact_type", "ref", "sha256", "size_bytes"})


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
        worktree_identity = (
            git.get("worktree_identity")
            if isinstance(git.get("worktree_identity"), dict)
            else {}
        )
        material["git"] = {
            "head": git.get("head"),
            "changed_path_set_sha256": (git.get("changed_paths") or {}).get(
                "set_sha256"
            )
            if isinstance(git.get("changed_paths"), dict)
            else None,
            "worktree_binding_status": worktree_identity.get("binding_status"),
            "worktree_inventory_sha256": worktree_identity.get(
                "inventory_sha256"
            ),
        }
    if "diagnostics" in roles:
        material["diagnostic_set_sha256"] = diagnostics.get("set_sha256")
    return canonical_sha256(material)


def preparation_identity(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") in {
        PREPARATION_SCHEMA_VERSION_V2,
        PREPARATION_SCHEMA_VERSION_V3,
    }:
        identity = {
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
                "machine_input_binding",
                "executor_spec",
                "derived_values",
                "result_contract",
                "next_action",
            )
        }
        if value.get("schema_version") == PREPARATION_SCHEMA_VERSION_V3:
            metrics = value.get("compiler_metrics")
            identity["compiler_metrics"] = (
                {
                    key: item
                    for key, item in metrics.items()
                    if key not in _DYNAMIC_COMPILER_METRIC_FIELDS
                }
                if isinstance(metrics, dict)
                else metrics
            )
            identity["precondition_fingerprints"] = value.get(
                "precondition_fingerprints"
            )
            identity["allowed_post_effect_selectors"] = value.get(
                "allowed_post_effect_selectors"
            )
        return identity
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
    if value.get("schema_version") in {
        PREPARATION_SCHEMA_VERSION_V2,
        PREPARATION_SCHEMA_VERSION_V3,
    }:
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


def durable_preparation_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Remove per-attempt CAS counters from immutable preparation content."""

    projected = dict(value)
    metrics = projected.get("compiler_metrics")
    if isinstance(metrics, dict):
        projected["compiler_metrics"] = {
            key: item
            for key, item in metrics.items()
            if key not in _DYNAMIC_COMPILER_METRIC_FIELDS
        }
    return projected


def require_expected_preparation(
    supplied: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    if canonical_bytes(trusted_preparation_material(supplied)) != canonical_bytes(
        trusted_preparation_material(expected)
    ):
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
    if version in {PREPARATION_SCHEMA_VERSION_V2, PREPARATION_SCHEMA_VERSION_V3}:
        if value.get("executor_kind") not in EXECUTOR_KINDS - {"system"}:
            raise ValueError("stage preparation has an invalid executor_kind")
    _validate_top_level_fields(value, version)
    identity = preparation_identity(value)
    expected = "stageprep-" + canonical_sha256(identity)[:32]
    if value.get("preparation_id") != expected:
        raise ValueError("stage preparation identity does not match its content")
    roles = value.get("fingerprint_roles")
    if not isinstance(roles, list):
        raise ValueError("stage preparation fingerprint_roles must be a list")
    if version in {PREPARATION_SCHEMA_VERSION_V2, PREPARATION_SCHEMA_VERSION_V3}:
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


def _validate_top_level_fields(value: dict[str, Any], version: int) -> None:
    if version == PREPARATION_SCHEMA_VERSION:
        expected = _V1_PREPARATION_FIELDS
    elif version == PREPARATION_SCHEMA_VERSION_V2:
        expected = _V2_V3_COMMON_PREPARATION_FIELDS | _CONTEXT_PREPARATION_FIELDS
    elif value.get("executor_kind") == "deterministic":
        expected = (
            _V2_V3_COMMON_PREPARATION_FIELDS
            | _MACHINE_PREPARATION_FIELDS
            | _V3_PRECONDITION_FIELDS
        )
    else:
        expected = (
            _V2_V3_COMMON_PREPARATION_FIELDS
            | _CONTEXT_PREPARATION_FIELDS
            | _V3_PRECONDITION_FIELDS
        )
    actual = set(value)
    if actual != expected:
        unexpected = sorted(actual - expected)
        missing = sorted(expected - actual)
        details = []
        if unexpected:
            details.append("unsupported=" + ",".join(unexpected))
        if missing:
            details.append("missing=" + ",".join(missing))
        raise ValueError(
            "stage preparation top-level fields are not closed: " + "; ".join(details)
        )


def _validate_binding(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"stage preparation {label} must be an object")
    if set(value) != _BINDING_FIELDS:
        raise ValueError(
            f"stage preparation {label} fields are not closed"
        )
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
    if "model_context" in value or "model_packet" in value:
        raise ValueError("v2 stage preparation must not embed context or packet bodies")
    if value.get("schema_version") == PREPARATION_SCHEMA_VERSION_V3 and value.get(
        "executor_kind"
    ) == "deterministic":
        if "context_binding" in value or "work_order_binding" in value:
            raise ValueError(
                "v3 deterministic preparation must not create model context or work order"
            )
        _validate_binding(value.get("machine_input_binding"), "machine_input_binding")
    else:
        _validate_binding(value.get("context_binding"), "context_binding")
        _validate_binding(value.get("work_order_binding"), "work_order_binding")
    if value.get("schema_version") == PREPARATION_SCHEMA_VERSION_V3:
        from .executor_registry import allowed_post_effect_selectors
        from .v2_specs import dependency_selectors

        from .executor_registry import executor_spec as registered_executor_spec

        supplied_executor_spec = value.get("executor_spec")
        try:
            registered = registered_executor_spec(
                str(value.get("target"))
            ).projection()
        except ValueError as exc:
            raise ValueError("v3 preparation target has no registered executor") from exc
        if supplied_executor_spec != registered:
            raise ValueError(
                "v3 preparation executor_spec does not match the registered projection"
            )
        metrics = value.get("compiler_metrics")
        if not isinstance(metrics, dict):
            raise ValueError("v3 preparation requires compiler_metrics")
        fingerprints = value.get("precondition_fingerprints")
        expected_selectors = dependency_selectors(str(value.get("target")))
        if (
            not isinstance(fingerprints, dict)
            or set(fingerprints) != set(expected_selectors)
            or any(
                not SHA256_PATTERN.fullmatch(str(digest or ""))
                for digest in fingerprints.values()
            )
        ):
            raise ValueError("v3 preparation precondition fingerprints are invalid")
        if value.get("allowed_post_effect_selectors") != list(
            allowed_post_effect_selectors(str(value.get("target")))
        ):
            raise ValueError("v3 preparation post-effect selector boundary differs")
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
    "PREPARATION_SCHEMA_VERSION_V3",
    "SUPPORTED_PREPARATION_SCHEMA_VERSIONS",
    "canonical_bytes",
    "canonical_sha256",
    "durable_preparation_projection",
    "leaf_count",
    "preparation_binding_sha256",
    "preparation_identity",
    "require_expected_preparation",
    "stale_preparation_result",
    "state_fingerprint",
    "trusted_preparation_material",
    "validate_preparation",
]
