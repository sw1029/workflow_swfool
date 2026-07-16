from __future__ import annotations

from ..runtime_dependencies import (
    bool_value,
    gate_allowed_task_kinds,
    row_root_family,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_decision_task_options(frame: _EvaluationFrame) -> None:
    (
        current_root_family_key, diagnostics_gate, failure_surface_gate, forced_retarget_gate,
        reachability_gate, registry_rows,
    ) = frame.require(
        'current_root_family_key', 'diagnostics_gate', 'failure_surface_gate',
        'forced_retarget_gate', 'reachability_gate', 'registry_rows',
    )
    envelope_thaw_streak = 0
    if bool_value(reachability_gate.get("envelope_thaw_item_required")):
        envelope_thaw_streak = 1
        for prior_row in reversed(registry_rows):
            if row_root_family(prior_row) != current_root_family_key:
                continue
            if bool_value(prior_row.get("envelope_thaw_item_required")):
                envelope_thaw_streak += 1
                continue
            break
    forced_task_options = list(forced_retarget_gate.get("forced_selected_task_options") or [])
    if bool_value(diagnostics_gate.get("instrumentation_supply_required")):
        existing_forced_kinds = gate_allowed_task_kinds({"forced_selected_task_options": forced_task_options})
        if not existing_forced_kinds.intersection({"instrumentation_supply", "execution_diagnostics_supply"}):
            forced_task_options.append(
                {
                    "selected_task_kind": "instrumentation_supply",
                    "task_kind": "instrumentation_supply",
                    "source": "diagnostics_unavailable_gate",
                    "actionable": True,
                    "failure_surface_count_key": failure_surface_gate.get("failure_surface_count_key"),
                    "diagnostics_unavailable_streak": diagnostics_gate.get("diagnostics_unavailable_streak"),
                    "instrumentation_trigger_threshold": diagnostics_gate.get("instrumentation_trigger_threshold"),
                }
            )
    forced_selected_task = forced_retarget_gate.get("forced_selected_task") or (forced_task_options[0] if forced_task_options else None)
    frame.update({
        "envelope_thaw_streak": envelope_thaw_streak,
        "forced_selected_task": forced_selected_task,
        "forced_task_options": forced_task_options,
    })
