"""Selection receipt for a compiler-resolved user-escalation authority delta."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selection_decision_store import (
    canonical_sha256,
    closed_object,
    normalize_binding,
    read_bound_bytes,
    read_bound_json,
)
from .selection_synthesis import validate_selection_synthesis
from .selection_trigger import validate_normal_cycle_trigger


DECISION_KEYS = {
    "schema_version",
    "artifact_kind",
    "decision_id",
    "decision_stage",
    "selection_trigger",
    "trigger_kind",
    "selection_synthesis",
    "authority_resolution",
    "synthesis_receipt_id",
    "outcome",
    "selected_task_id",
    "task_source",
    "evidence_manifest_sha256",
    "decision_sha256",
}
RECEIPT_KEYS = {
    "schema_version",
    "artifact_kind",
    "receipt_id",
    "selection_trigger",
    "trigger_kind",
    "trigger_id",
    "selection_decision",
    "selection_synthesis",
    "authority_resolution",
    "task_source",
    "resolution_kind",
    "synthesis_receipt_id",
    "input_evidence_manifest_sha256",
    "outcome",
    "selected_task_id",
    "not_goal_truth",
    "not_authority",
    "not_validation_evidence",
    "not_completion_evidence",
    "mutation_performed",
    "receipt_sha256",
}


def _cas_binding(
    value: Any,
    category: str,
    label: str,
    *,
    suffix: str = ".json",
) -> dict[str, str]:
    binding = normalize_binding(value, label)
    expected = f".task/selection_reentry/{category}/sha256/{binding['sha256']}{suffix}"
    if binding["ref"] != expected:
        raise ValueError(f"{label} must use its exact authority-reentry CAS path")
    return binding


def _validated_values(
    root: Path,
    trigger_binding_value: Any,
    trigger_value: Any,
    synthesis_binding_value: Any,
    synthesis_value: Any,
    resolution_binding_value: Any,
    resolution_value: Any,
    task_source_binding_value: Any,
    *,
    prospective: bool,
    expected_active_prepare: Any = None,
) -> tuple[
    dict[str, str],
    dict[str, Any],
    dict[str, str],
    dict[str, Any],
    dict[str, str],
    dict[str, Any],
    dict[str, str],
]:
    trigger_binding = _cas_binding(
        trigger_binding_value,
        "triggers",
        "authority-reentry selection trigger",
    )
    synthesis_binding = _cas_binding(
        synthesis_binding_value,
        "syntheses",
        "authority-reentry selection synthesis",
    )
    resolution_binding = _cas_binding(
        resolution_binding_value,
        "resolutions",
        "authority-reentry resolution",
    )
    task_source = _cas_binding(
        task_source_binding_value,
        "task_sources",
        "authority-reentry task source",
        suffix=".md",
    )
    trigger = validate_normal_cycle_trigger(
        root,
        trigger_value,
        expected_active_prepare=expected_active_prepare,
    )
    synthesis = validate_selection_synthesis(root, synthesis_value)
    if not isinstance(resolution_value, dict):
        raise ValueError("authority-reentry resolution must be an object")
    if prospective:
        from .selection_authority_reentry import (
            validate_authority_reentry_resolution_seal,
        )

        resolution = validate_authority_reentry_resolution_seal(resolution_value)
    else:
        from .selection_authority_reentry import (
            validate_authority_reentry_resolution,
        )

        resolution = validate_authority_reentry_resolution(
            root,
            resolution_value,
            expected_active_prepare=expected_active_prepare,
        )
        read_bound_bytes(root, task_source, "authority-reentry task source")
    if (
        resolution.get("selection_trigger") != trigger_binding
        or resolution.get("source_selection_synthesis") != synthesis_binding
        or resolution.get("task_source") != task_source
        or resolution.get("source_cycle_id") != trigger.get("cycle_id")
        or resolution.get("source_outcome") != "user_escalation"
        or synthesis.get("selection_outcome") != "user_escalation"
        or synthesis.get("selected_task_id") is not None
        or synthesis.get("selected_candidate_id") != ""
    ):
        raise ValueError("authority-reentry resolution dependency binding differs")
    return (
        trigger_binding,
        trigger,
        synthesis_binding,
        synthesis,
        resolution_binding,
        resolution,
        task_source,
    )


def _decision_core(
    trigger_binding: dict[str, str],
    synthesis_binding: dict[str, str],
    resolution_binding: dict[str, str],
    synthesis: dict[str, Any],
    resolution: dict[str, Any],
    task_source: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "artifact_kind": "preliminary_selection_decision",
        "decision_stage": "authority_resolution_selection",
        "selection_trigger": trigger_binding,
        "trigger_kind": "normal_cycle",
        "selection_synthesis": synthesis_binding,
        "authority_resolution": resolution_binding,
        "synthesis_receipt_id": synthesis["synthesis_receipt_id"],
        "outcome": "selected",
        "selected_task_id": resolution["selected_task_id"],
        "task_source": task_source,
        "evidence_manifest_sha256": synthesis["input_evidence_manifest_sha256"],
    }


def render_preliminary_selection_decision_v3_from_values(
    root: Path,
    trigger_binding_value: dict[str, str],
    trigger_value: dict[str, Any],
    synthesis_binding_value: dict[str, str],
    synthesis_value: dict[str, Any],
    resolution_binding_value: dict[str, str],
    resolution_value: dict[str, Any],
    task_source_binding_value: dict[str, str],
) -> dict[str, Any]:
    """Render a selected decision from one prospective, sealed resolution."""

    (
        trigger_binding,
        _trigger,
        synthesis_binding,
        synthesis,
        resolution_binding,
        resolution,
        task_source,
    ) = _validated_values(
        root,
        trigger_binding_value,
        trigger_value,
        synthesis_binding_value,
        synthesis_value,
        resolution_binding_value,
        resolution_value,
        task_source_binding_value,
        prospective=True,
    )
    core = _decision_core(
        trigger_binding,
        synthesis_binding,
        resolution_binding,
        synthesis,
        resolution,
        task_source,
    )
    decision_id = "preliminary-selection-v3-" + canonical_sha256(core)[:24]
    body = {**core, "decision_id": decision_id}
    return {**body, "decision_sha256": canonical_sha256(body)}


def validate_preliminary_selection_decision_v3(
    root: Path,
    value: Any,
    *,
    expected_active_prepare: Any = None,
) -> dict[str, Any]:
    decision = closed_object(value, DECISION_KEYS, "selection decision v3")
    trigger_binding = _cas_binding(
        decision.get("selection_trigger"),
        "triggers",
        "authority-reentry selection trigger",
    )
    _, trigger = read_bound_json(
        root, trigger_binding, "authority-reentry selection trigger"
    )
    synthesis_binding = _cas_binding(
        decision.get("selection_synthesis"),
        "syntheses",
        "authority-reentry selection synthesis",
    )
    _, synthesis = read_bound_json(
        root, synthesis_binding, "authority-reentry selection synthesis"
    )
    resolution_binding = _cas_binding(
        decision.get("authority_resolution"),
        "resolutions",
        "authority-reentry resolution",
    )
    _, resolution = read_bound_json(
        root, resolution_binding, "authority-reentry resolution"
    )
    (
        trigger_binding,
        _trigger,
        synthesis_binding,
        synthesis,
        resolution_binding,
        resolution,
        task_source,
    ) = _validated_values(
        root,
        trigger_binding,
        trigger,
        synthesis_binding,
        synthesis,
        resolution_binding,
        resolution,
        decision.get("task_source"),
        prospective=False,
        expected_active_prepare=expected_active_prepare,
    )
    core = _decision_core(
        trigger_binding,
        synthesis_binding,
        resolution_binding,
        synthesis,
        resolution,
        task_source,
    )
    expected_id = "preliminary-selection-v3-" + canonical_sha256(core)[:24]
    body = {**core, "decision_id": expected_id}
    sealed = {**body, "decision_sha256": canonical_sha256(body)}
    if decision != sealed:
        raise ValueError("selection decision v3 integrity failed")
    return sealed


def _receipt_core(
    trigger_binding: dict[str, str],
    trigger: dict[str, Any],
    decision_binding: dict[str, str],
    synthesis_binding: dict[str, str],
    synthesis: dict[str, Any],
    resolution_binding: dict[str, str],
    resolution: dict[str, Any],
    task_source: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "artifact_kind": "selection_decision_receipt",
        "selection_trigger": trigger_binding,
        "trigger_kind": "normal_cycle",
        "trigger_id": trigger["trigger_id"],
        "selection_decision": decision_binding,
        "selection_synthesis": synthesis_binding,
        "authority_resolution": resolution_binding,
        "task_source": task_source,
        "resolution_kind": "user_escalation_authority_resolution",
        "synthesis_receipt_id": synthesis["synthesis_receipt_id"],
        "input_evidence_manifest_sha256": synthesis["input_evidence_manifest_sha256"],
        "outcome": "selected",
        "selected_task_id": resolution["selected_task_id"],
        "not_goal_truth": True,
        "not_authority": True,
        "not_validation_evidence": True,
        "not_completion_evidence": True,
        "mutation_performed": False,
    }


def render_selection_decision_receipt_v3_from_values(
    root: Path,
    trigger_binding_value: dict[str, str],
    trigger_value: dict[str, Any],
    synthesis_binding_value: dict[str, str],
    synthesis_value: dict[str, Any],
    resolution_binding_value: dict[str, str],
    resolution_value: dict[str, Any],
    decision_binding_value: dict[str, str],
    decision_value: dict[str, Any],
    task_source_binding_value: dict[str, str],
) -> dict[str, Any]:
    """Render a receipt from one complete prospective dependency set."""

    (
        trigger_binding,
        trigger,
        synthesis_binding,
        synthesis,
        resolution_binding,
        resolution,
        task_source,
    ) = _validated_values(
        root,
        trigger_binding_value,
        trigger_value,
        synthesis_binding_value,
        synthesis_value,
        resolution_binding_value,
        resolution_value,
        task_source_binding_value,
        prospective=True,
    )
    decision_binding = _cas_binding(
        decision_binding_value,
        "decisions",
        "selection decision v3",
    )
    expected_decision = render_preliminary_selection_decision_v3_from_values(
        root,
        trigger_binding,
        trigger,
        synthesis_binding,
        synthesis,
        resolution_binding,
        resolution,
        task_source,
    )
    if decision_value != expected_decision:
        raise ValueError("selection decision v3 integrity failed")
    core = _receipt_core(
        trigger_binding,
        trigger,
        decision_binding,
        synthesis_binding,
        synthesis,
        resolution_binding,
        resolution,
        task_source,
    )
    receipt_id = "selection-decision-v3-" + canonical_sha256(core)[:24]
    body = {**core, "receipt_id": receipt_id}
    return {**body, "receipt_sha256": canonical_sha256(body)}


def validate_selection_decision_receipt_v3(
    root: Path,
    value: Any,
    *,
    expected_active_prepare: Any = None,
) -> dict[str, Any]:
    receipt = closed_object(value, RECEIPT_KEYS, "selection decision receipt v3")
    decision_binding = _cas_binding(
        receipt.get("selection_decision"),
        "decisions",
        "selection decision v3",
    )
    _, decision_value = read_bound_json(root, decision_binding, "selection decision v3")
    decision = validate_preliminary_selection_decision_v3(
        root,
        decision_value,
        expected_active_prepare=expected_active_prepare,
    )
    trigger_binding = _cas_binding(
        receipt.get("selection_trigger"),
        "triggers",
        "authority-reentry selection trigger",
    )
    _, trigger = read_bound_json(
        root, trigger_binding, "authority-reentry selection trigger"
    )
    synthesis_binding = _cas_binding(
        receipt.get("selection_synthesis"),
        "syntheses",
        "authority-reentry selection synthesis",
    )
    _, synthesis = read_bound_json(
        root, synthesis_binding, "authority-reentry selection synthesis"
    )
    resolution_binding = _cas_binding(
        receipt.get("authority_resolution"),
        "resolutions",
        "authority-reentry resolution",
    )
    _, resolution = read_bound_json(
        root, resolution_binding, "authority-reentry resolution"
    )
    (
        trigger_binding,
        trigger,
        synthesis_binding,
        synthesis,
        resolution_binding,
        resolution,
        task_source,
    ) = _validated_values(
        root,
        trigger_binding,
        trigger,
        synthesis_binding,
        synthesis,
        resolution_binding,
        resolution,
        receipt.get("task_source"),
        prospective=False,
        expected_active_prepare=expected_active_prepare,
    )
    if (
        decision.get("selection_trigger") != trigger_binding
        or decision.get("selection_synthesis") != synthesis_binding
        or decision.get("authority_resolution") != resolution_binding
        or decision.get("task_source") != task_source
    ):
        raise ValueError("selection decision receipt v3 dependency binding differs")
    core = _receipt_core(
        trigger_binding,
        trigger,
        decision_binding,
        synthesis_binding,
        synthesis,
        resolution_binding,
        resolution,
        task_source,
    )
    expected_id = "selection-decision-v3-" + canonical_sha256(core)[:24]
    body = {**core, "receipt_id": expected_id}
    sealed = {**body, "receipt_sha256": canonical_sha256(body)}
    if receipt != sealed:
        raise ValueError("selection decision receipt v3 integrity failed")
    return sealed


__all__ = (
    "DECISION_KEYS",
    "RECEIPT_KEYS",
    "render_preliminary_selection_decision_v3_from_values",
    "render_selection_decision_receipt_v3_from_values",
    "validate_preliminary_selection_decision_v3",
    "validate_selection_decision_receipt_v3",
)
