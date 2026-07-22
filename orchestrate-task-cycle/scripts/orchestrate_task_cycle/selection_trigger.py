"""Exact normal-cycle trigger for derive selection publication."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .selection_decision_store import (
    SHA256,
    canonical_sha256,
    closed_object,
    normalize_binding,
    read_bound_bytes,
)
from .selection_trigger_evidence import (
    render_publication_bootstrap,
    validate_current_owner_bindings,
    validate_cycle_finalization,
    validate_derive_result,
    validate_publication_head,
    validate_schema_pre_derive,
)


CYCLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
TRIGGER_KEYS = {
    "schema_version",
    "artifact_kind",
    "trigger_kind",
    "trigger_id",
    "cycle_id",
    "cycle_finalization",
    "schema_pre_derive",
    "derive_result",
    "current_task",
    "task_index",
    "publication_head",
    "input_evidence_manifest_sha256",
    "not_goal_truth",
    "not_authority",
    "not_validation_evidence",
    "mutation_performed",
    "trigger_sha256",
}
BINDING_FIELDS = (
    "cycle_finalization",
    "schema_pre_derive",
    "derive_result",
    "current_task",
    "task_index",
    "publication_head",
)


def _validated_bindings(
    root: Path,
    cycle_id: str,
    values: dict[str, Any],
    input_evidence_manifest_sha256: str,
    *,
    expected_active_prepare: Any = None,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for field in BINDING_FIELDS:
        binding = normalize_binding(values.get(field), field.replace("_", " "))
        read_bound_bytes(root, binding, field.replace("_", " "))
        result[field] = binding
    validate_cycle_finalization(root, cycle_id, result["cycle_finalization"])
    validate_schema_pre_derive(root, cycle_id, result["schema_pre_derive"])
    validate_derive_result(
        root,
        cycle_id,
        result["derive_result"],
        input_evidence_manifest_sha256,
    )
    validate_current_owner_bindings(
        root, result["current_task"], result["task_index"]
    )
    validate_publication_head(
        root,
        cycle_id,
        result["publication_head"],
        result["current_task"],
        result["task_index"],
        expected_active_prepare=expected_active_prepare,
    )
    return result


def render_normal_cycle_trigger(
    root: Path,
    *,
    cycle_id: str,
    cycle_finalization: dict[str, str],
    schema_pre_derive: dict[str, str],
    derive_result: dict[str, str],
    current_task: dict[str, str],
    task_index: dict[str, str],
    publication_head: dict[str, str],
    input_evidence_manifest_sha256: str,
) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    if not CYCLE_ID.fullmatch(cycle_id):
        raise ValueError("normal-cycle selection trigger cycle ID is invalid")
    if not SHA256.fullmatch(str(input_evidence_manifest_sha256 or "")):
        raise ValueError("normal-cycle selection trigger evidence digest is invalid")
    bindings = _validated_bindings(
        root,
        cycle_id,
        {
            "cycle_finalization": cycle_finalization,
            "schema_pre_derive": schema_pre_derive,
            "derive_result": derive_result,
            "current_task": current_task,
            "task_index": task_index,
            "publication_head": publication_head,
        },
        input_evidence_manifest_sha256,
    )
    core = {
        "schema_version": 1,
        "artifact_kind": "normal_cycle_selection_trigger",
        "trigger_kind": "normal_cycle",
        "cycle_id": cycle_id,
        **bindings,
        "input_evidence_manifest_sha256": input_evidence_manifest_sha256,
        "not_goal_truth": True,
        "not_authority": True,
        "not_validation_evidence": True,
        "mutation_performed": False,
    }
    trigger_id = "normal-selection-trigger-" + canonical_sha256(core)[:24]
    body = {**core, "trigger_id": trigger_id}
    return {**body, "trigger_sha256": canonical_sha256(body)}


def validate_normal_cycle_trigger(
    root: Path, value: Any, *, expected_active_prepare: Any = None
) -> dict[str, Any]:
    trigger = closed_object(value, TRIGGER_KEYS, "normal-cycle selection trigger")
    if (
        trigger.get("schema_version") != 1
        or trigger.get("artifact_kind") != "normal_cycle_selection_trigger"
        or trigger.get("trigger_kind") != "normal_cycle"
        or not CYCLE_ID.fullmatch(str(trigger.get("cycle_id") or ""))
        or not SHA256.fullmatch(
            str(trigger.get("input_evidence_manifest_sha256") or "")
        )
        or trigger.get("not_goal_truth") is not True
        or trigger.get("not_authority") is not True
        or trigger.get("not_validation_evidence") is not True
        or trigger.get("mutation_performed") is not False
    ):
        raise ValueError("normal-cycle selection trigger contract is invalid")
    bindings = _validated_bindings(
        root,
        trigger["cycle_id"],
        trigger,
        trigger["input_evidence_manifest_sha256"],
        expected_active_prepare=expected_active_prepare,
    )
    core = {
        "schema_version": 1,
        "artifact_kind": "normal_cycle_selection_trigger",
        "trigger_kind": "normal_cycle",
        "cycle_id": trigger["cycle_id"],
        **bindings,
        "input_evidence_manifest_sha256": trigger[
            "input_evidence_manifest_sha256"
        ],
        "not_goal_truth": True,
        "not_authority": True,
        "not_validation_evidence": True,
        "mutation_performed": False,
    }
    expected_id = "normal-selection-trigger-" + canonical_sha256(core)[:24]
    body = {**core, "trigger_id": expected_id}
    sealed = {**body, "trigger_sha256": canonical_sha256(body)}
    if trigger != sealed:
        raise ValueError("normal-cycle selection trigger integrity failed")
    return sealed


__all__ = (
    "render_normal_cycle_trigger",
    "render_publication_bootstrap",
    "validate_normal_cycle_trigger",
)
