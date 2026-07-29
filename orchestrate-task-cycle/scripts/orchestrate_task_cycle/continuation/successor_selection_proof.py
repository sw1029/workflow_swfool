"""Historical exact proof for a settled schema-v2 successor selection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..selected_successor_predecessor_snapshot import (
    validate_plan_owned_predecessor_snapshot,
)
from ..selection_decision_receipt_v2 import DECISION_KEYS, RECEIPT_KEYS
from ..selection_decision_store import (
    canonical_sha256,
    closed_object,
    normalize_binding,
    read_bound_json,
)
from ..selection_synthesis import validate_selection_synthesis
from ..selection_trigger import (
    BINDING_FIELDS,
    CYCLE_ID,
    TRIGGER_KEYS,
)
from ..selection_trigger_evidence import (
    BOOTSTRAP_KEYS,
    validate_cycle_finalization,
    validate_derive_result,
    validate_schema_pre_derive,
)


def _bootstrap(
    root: Path,
    binding: dict[str, str],
    *,
    cycle_id: str,
    current_task: dict[str, str],
    task_index: dict[str, str],
) -> None:
    _path, value = read_bound_json(
        root, binding, "historical selection publication bootstrap"
    )
    bootstrap = closed_object(
        value, BOOTSTRAP_KEYS, "historical selection publication bootstrap"
    )
    core = {
        "schema_version": 1,
        "artifact_kind": "normal_cycle_selection_publication_bootstrap",
        "cycle_id": cycle_id,
        "publication_status": "not_initialized",
        "current_task": current_task,
        "task_index": task_index,
        "not_goal_truth": True,
        "not_authority": True,
        "not_validation_evidence": True,
        "mutation_performed": False,
    }
    bootstrap_id = "selection-publication-bootstrap-" + canonical_sha256(core)[:24]
    body = {**core, "bootstrap_id": bootstrap_id}
    expected = {**body, "bootstrap_sha256": canonical_sha256(body)}
    if bootstrap != expected:
        raise ValueError("historical publication bootstrap integrity failed")


def _trigger(
    root: Path,
    value: Any,
    *,
    cycle_id: str,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    trigger = closed_object(value, TRIGGER_KEYS, "historical selection trigger")
    if (
        trigger.get("schema_version") != 1
        or trigger.get("artifact_kind") != "normal_cycle_selection_trigger"
        or trigger.get("trigger_kind") != "normal_cycle"
        or trigger.get("cycle_id") != cycle_id
        or not CYCLE_ID.fullmatch(cycle_id)
        or trigger.get("not_goal_truth") is not True
        or trigger.get("not_authority") is not True
        or trigger.get("not_validation_evidence") is not True
        or trigger.get("mutation_performed") is not False
    ):
        raise ValueError("historical selection trigger contract differs")
    bindings = {
        field: normalize_binding(
            trigger.get(field), f"historical selection {field}"
        )
        for field in BINDING_FIELDS
    }
    snapshot = validate_plan_owned_predecessor_snapshot(root, bundle)
    current_task = bindings["current_task"]
    if current_task != {"ref": "task.md", "sha256": snapshot["sha256"]}:
        raise ValueError("historical selection predecessor differs")
    from manage_task_state_index.state.transition_plan_contract import (
        load_transition_plan,
    )

    plan_binding = normalize_binding(
        bundle["task_state_plan"], "historical successor plan"
    )
    plan_path, plan, plan_sha = load_transition_plan(root, plan_binding["ref"])
    if plan_binding != {
        "ref": plan_path.relative_to(root).as_posix(),
        "sha256": plan_sha,
    }:
        raise ValueError("historical successor plan binding differs")
    ledger = plan.get("ledger")
    if (
        not isinstance(ledger, dict)
        or bindings["task_index"]
        != {
            "ref": ".task/index.jsonl",
            "sha256": ledger.get("before_sha256"),
        }
    ):
        raise ValueError("historical selection task index differs")
    validate_cycle_finalization(root, cycle_id, bindings["cycle_finalization"])
    validate_schema_pre_derive(root, cycle_id, bindings["schema_pre_derive"])
    validate_derive_result(
        root,
        cycle_id,
        bindings["derive_result"],
        trigger["input_evidence_manifest_sha256"],
    )
    _bootstrap(
        root,
        bindings["publication_head"],
        cycle_id=cycle_id,
        current_task=current_task,
        task_index=bindings["task_index"],
    )
    core = {
        "schema_version": 1,
        "artifact_kind": "normal_cycle_selection_trigger",
        "trigger_kind": "normal_cycle",
        "cycle_id": cycle_id,
        **bindings,
        "input_evidence_manifest_sha256": trigger[
            "input_evidence_manifest_sha256"
        ],
        "not_goal_truth": True,
        "not_authority": True,
        "not_validation_evidence": True,
        "mutation_performed": False,
    }
    trigger_id = "normal-selection-trigger-" + canonical_sha256(core)[:24]
    body = {**core, "trigger_id": trigger_id}
    expected = {**body, "trigger_sha256": canonical_sha256(body)}
    if trigger != expected:
        raise ValueError("historical selection trigger integrity failed")
    return trigger


def _decision(
    root: Path,
    binding: dict[str, str],
    trigger_binding: dict[str, str],
    trigger: dict[str, Any],
) -> dict[str, Any]:
    _path, raw = read_bound_json(root, binding, "historical selection decision")
    decision = closed_object(raw, DECISION_KEYS, "historical selection decision")
    synthesis_binding = normalize_binding(
        decision.get("selection_synthesis"), "historical selection synthesis"
    )
    _synthesis_path, synthesis_raw = read_bound_json(
        root, synthesis_binding, "historical selection synthesis"
    )
    synthesis = validate_selection_synthesis(root, synthesis_raw)
    core = {
        "schema_version": 2,
        "artifact_kind": "preliminary_selection_decision",
        "decision_stage": "preliminary_selection",
        "selection_trigger": trigger_binding,
        "trigger_kind": trigger["trigger_kind"],
        "trigger_id": trigger["trigger_id"],
        "selection_synthesis": synthesis_binding,
        "synthesis_receipt_id": synthesis["synthesis_receipt_id"],
        "outcome": synthesis["selection_outcome"],
        "selected_task_id": synthesis["selected_task_id"],
        "evidence_manifest_sha256": synthesis[
            "input_evidence_manifest_sha256"
        ],
    }
    decision_id = "preliminary-selection-v2-" + canonical_sha256(core)[:24]
    body = {**core, "decision_id": decision_id}
    expected = {**body, "decision_sha256": canonical_sha256(body)}
    if decision != expected:
        raise ValueError("historical selection decision integrity failed")
    return decision


def validate_historical_selection_v2(
    root: Path,
    binding: dict[str, str],
    receipt: dict[str, Any],
    *,
    cycle_id: str,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    """Validate immutable selection lineage using the settled predecessor plan."""

    selected = closed_object(
        receipt, RECEIPT_KEYS, "historical selection receipt"
    )
    trigger_binding = normalize_binding(
        selected.get("selection_trigger"), "historical selection trigger"
    )
    _trigger_path, trigger_raw = read_bound_json(
        root, trigger_binding, "historical selection trigger"
    )
    trigger = _trigger(root, trigger_raw, cycle_id=cycle_id, bundle=bundle)
    decision_binding = normalize_binding(
        selected.get("selection_decision"), "historical selection decision"
    )
    decision = _decision(
        root, decision_binding, trigger_binding, trigger
    )
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
    expected = {**body, "receipt_sha256": canonical_sha256(body)}
    if selected != expected:
        raise ValueError("historical selection receipt integrity failed")
    # Reopen the exact bound bytes once more after the lineage walk.
    _path, reopened = read_bound_json(
        root, binding, "historical selection receipt replay"
    )
    if reopened != selected:
        raise ValueError("historical selection receipt changed")
    return selected


__all__ = ("validate_historical_selection_v2",)
