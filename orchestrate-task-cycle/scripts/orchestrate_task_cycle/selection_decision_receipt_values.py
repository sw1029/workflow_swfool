"""Pure prospective rendering for terminal selection-decision artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selection_decision_receipt import (
    _decision_core,
    _normalize_outcome,
    _persisted_trigger_binding,
    _receipt_core,
    _trigger_binding,
    _validate_trigger_tick,
)
from .selection_decision_store import (
    canonical_sha256,
    normalize_binding,
)
from .selection_synthesis import validate_selection_synthesis


def render_preliminary_selection_decision_from_values(
    root: Path,
    trigger_tick: dict[str, Any],
    selection_synthesis_binding: dict[str, str],
    synthesis_value: dict[str, Any],
) -> dict[str, Any]:
    """Render from prospective synthesis bytes after complete validation."""

    _validate_trigger_tick(trigger_tick)
    synthesis_binding = normalize_binding(
        selection_synthesis_binding, "selection synthesis"
    )
    synthesis = validate_selection_synthesis(root, synthesis_value)
    outcome, selected_task_id = _normalize_outcome(
        synthesis["selection_outcome"], synthesis["selected_task_id"]
    )
    core = _decision_core(
        _trigger_binding(trigger_tick),
        synthesis_binding,
        synthesis["synthesis_receipt_id"],
        outcome,
        selected_task_id,
        synthesis["input_evidence_manifest_sha256"],
    )
    decision_id = "preliminary-selection-" + canonical_sha256(core)[:24]
    body = {**core, "decision_id": decision_id}
    return {**body, "decision_sha256": canonical_sha256(body)}


def render_selection_decision_receipt_from_values(
    root: Path,
    trigger_tick: dict[str, Any],
    trigger_tick_binding: dict[str, str],
    selection_decision_binding: dict[str, str],
    decision_value: dict[str, Any],
    synthesis_value: dict[str, Any],
) -> dict[str, Any]:
    """Render a receipt from a fully validated prospective dependency set."""

    _validate_trigger_tick(trigger_tick)
    persisted_trigger = _persisted_trigger_binding(
        root, trigger_tick, trigger_tick_binding
    )
    decision_binding = normalize_binding(
        selection_decision_binding, "preliminary selection decision"
    )
    if not isinstance(decision_value, dict):
        raise ValueError("preliminary selection decision must be an object")
    decision = render_preliminary_selection_decision_from_values(
        root,
        trigger_tick,
        decision_value.get("selection_synthesis"),
        synthesis_value,
    )
    if decision_value != decision:
        raise ValueError("derive selection decision integrity check failed")
    core = _receipt_core(
        _trigger_binding(trigger_tick),
        persisted_trigger,
        decision_binding,
        decision["synthesis_receipt_id"],
        decision["evidence_manifest_sha256"],
        decision["outcome"],
        decision["selected_task_id"],
    )
    receipt_id = "selection-decision-" + canonical_sha256(core)[:24]
    body = {**core, "receipt_id": receipt_id}
    return {**body, "receipt_sha256": canonical_sha256(body)}


__all__ = (
    "render_preliminary_selection_decision_from_values",
    "render_selection_decision_receipt_from_values",
)
