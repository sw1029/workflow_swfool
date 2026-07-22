"""Selection decision receipt bound to a generic exact trigger."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .selection_decision_store import (
    SHA256,
    canonical_sha256,
    closed_object,
    normalize_binding,
    read_bound_json,
)
from .selection_synthesis import validate_selection_synthesis
from .selection_trigger import validate_normal_cycle_trigger


OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
OUTCOMES = frozenset(
    {"selected", "terminal_wait", "terminal_blocked", "user_escalation"}
)
DECISION_KEYS = {
    "schema_version",
    "artifact_kind",
    "decision_id",
    "decision_stage",
    "selection_trigger",
    "trigger_kind",
    "trigger_id",
    "selection_synthesis",
    "synthesis_receipt_id",
    "outcome",
    "selected_task_id",
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


def _trigger(
    root: Path, value: Any
) -> tuple[dict[str, str], dict[str, Any]]:
    binding = normalize_binding(value, "normal-cycle selection trigger")
    _, raw = read_bound_json(root, binding, "normal-cycle selection trigger")
    return binding, validate_normal_cycle_trigger(root, raw)


def _synthesis(
    root: Path, value: Any
) -> tuple[dict[str, str], dict[str, Any]]:
    binding = normalize_binding(value, "selection synthesis")
    _, raw = read_bound_json(root, binding, "selection synthesis")
    return binding, validate_selection_synthesis(root, raw)


def _outcome(value: Any, task_value: Any) -> tuple[str, str | None]:
    if value not in OUTCOMES:
        raise ValueError("selection decision outcome is invalid")
    if value == "selected":
        if not isinstance(task_value, str) or not OPAQUE_ID.fullmatch(task_value):
            raise ValueError("selected decision requires a bounded task ID")
        return value, task_value
    if task_value is not None:
        raise ValueError("non-selected decision cannot carry a task ID")
    return value, None


def render_preliminary_selection_decision_v2(
    root: Path,
    trigger_binding_value: dict[str, str],
    synthesis_binding_value: dict[str, str],
) -> dict[str, Any]:
    trigger_binding, trigger = _trigger(root, trigger_binding_value)
    synthesis_binding, synthesis = _synthesis(root, synthesis_binding_value)
    outcome, selected_task_id = _outcome(
        synthesis["selection_outcome"], synthesis["selected_task_id"]
    )
    core = {
        "schema_version": 2,
        "artifact_kind": "preliminary_selection_decision",
        "decision_stage": "preliminary_selection",
        "selection_trigger": trigger_binding,
        "trigger_kind": trigger["trigger_kind"],
        "trigger_id": trigger["trigger_id"],
        "selection_synthesis": synthesis_binding,
        "synthesis_receipt_id": synthesis["synthesis_receipt_id"],
        "outcome": outcome,
        "selected_task_id": selected_task_id,
        "evidence_manifest_sha256": synthesis[
            "input_evidence_manifest_sha256"
        ],
    }
    decision_id = "preliminary-selection-v2-" + canonical_sha256(core)[:24]
    body = {**core, "decision_id": decision_id}
    return {**body, "decision_sha256": canonical_sha256(body)}


def validate_preliminary_selection_decision_v2(
    root: Path, value: Any
) -> dict[str, Any]:
    decision = closed_object(value, DECISION_KEYS, "selection decision v2")
    trigger_binding, trigger = _trigger(root, decision.get("selection_trigger"))
    synthesis_binding, synthesis = _synthesis(
        root, decision.get("selection_synthesis")
    )
    outcome, selected_task_id = _outcome(
        synthesis["selection_outcome"], synthesis["selected_task_id"]
    )
    core = {
        "schema_version": 2,
        "artifact_kind": "preliminary_selection_decision",
        "decision_stage": "preliminary_selection",
        "selection_trigger": trigger_binding,
        "trigger_kind": trigger["trigger_kind"],
        "trigger_id": trigger["trigger_id"],
        "selection_synthesis": synthesis_binding,
        "synthesis_receipt_id": synthesis["synthesis_receipt_id"],
        "outcome": outcome,
        "selected_task_id": selected_task_id,
        "evidence_manifest_sha256": synthesis[
            "input_evidence_manifest_sha256"
        ],
    }
    expected_id = "preliminary-selection-v2-" + canonical_sha256(core)[:24]
    body = {**core, "decision_id": expected_id}
    sealed = {**body, "decision_sha256": canonical_sha256(body)}
    if decision != sealed:
        raise ValueError("selection decision v2 integrity failed")
    return sealed


def render_selection_decision_receipt_v2(
    root: Path,
    trigger_binding_value: dict[str, str],
    decision_binding_value: dict[str, str],
) -> dict[str, Any]:
    trigger_binding, trigger = _trigger(root, trigger_binding_value)
    decision_binding = normalize_binding(
        decision_binding_value, "selection decision v2"
    )
    _, raw = read_bound_json(root, decision_binding, "selection decision v2")
    decision = validate_preliminary_selection_decision_v2(root, raw)
    if decision["selection_trigger"] != trigger_binding:
        raise ValueError("selection decision v2 binds another trigger")
    core = {
        "schema_version": 2,
        "artifact_kind": "selection_decision_receipt",
        "selection_trigger": trigger_binding,
        "trigger_kind": trigger["trigger_kind"],
        "trigger_id": trigger["trigger_id"],
        "selection_decision": decision_binding,
        "synthesis_receipt_id": decision["synthesis_receipt_id"],
        "input_evidence_manifest_sha256": decision[
            "evidence_manifest_sha256"
        ],
        "outcome": decision["outcome"],
        "selected_task_id": decision["selected_task_id"],
        "not_goal_truth": True,
        "not_authority": True,
        "not_validation_evidence": True,
        "not_completion_evidence": True,
        "mutation_performed": False,
    }
    receipt_id = "selection-decision-v2-" + canonical_sha256(core)[:24]
    body = {**core, "receipt_id": receipt_id}
    return {**body, "receipt_sha256": canonical_sha256(body)}


def validate_selection_decision_receipt_v2(
    root: Path, value: Any
) -> dict[str, Any]:
    receipt = closed_object(value, RECEIPT_KEYS, "selection decision receipt v2")
    trigger_binding, trigger = _trigger(root, receipt.get("selection_trigger"))
    decision_binding = normalize_binding(
        receipt.get("selection_decision"), "selection decision v2"
    )
    _, raw = read_bound_json(root, decision_binding, "selection decision v2")
    decision = validate_preliminary_selection_decision_v2(root, raw)
    core = {
        "schema_version": 2,
        "artifact_kind": "selection_decision_receipt",
        "selection_trigger": trigger_binding,
        "trigger_kind": trigger["trigger_kind"],
        "trigger_id": trigger["trigger_id"],
        "selection_decision": decision_binding,
        "synthesis_receipt_id": decision["synthesis_receipt_id"],
        "input_evidence_manifest_sha256": decision[
            "evidence_manifest_sha256"
        ],
        "outcome": decision["outcome"],
        "selected_task_id": decision["selected_task_id"],
        "not_goal_truth": True,
        "not_authority": True,
        "not_validation_evidence": True,
        "not_completion_evidence": True,
        "mutation_performed": False,
    }
    if decision["selection_trigger"] != trigger_binding:
        raise ValueError("selection decision receipt v2 trigger disagrees")
    expected_id = "selection-decision-v2-" + canonical_sha256(core)[:24]
    body = {**core, "receipt_id": expected_id}
    sealed = {**body, "receipt_sha256": canonical_sha256(body)}
    if receipt != sealed:
        raise ValueError("selection decision receipt v2 integrity failed")
    return sealed


__all__ = (
    "render_preliminary_selection_decision_v2",
    "render_selection_decision_receipt_v2",
    "validate_selection_decision_receipt_v2",
)
