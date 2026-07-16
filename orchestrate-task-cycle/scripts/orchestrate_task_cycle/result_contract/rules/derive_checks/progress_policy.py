from __future__ import annotations

from .shared import (
    add,
    advice_handling_rationale_present,
    boolish,
    first_present,
    has_value,
    number_value,
)
from .state import DeriveFacts


def _check_progress_policy_part_01(facts: DeriveFacts) -> None:
    findings = facts.findings
    forced_kind = facts.forced_kind
    mode = facts.mode
    result = facts.result
    selected_kind = facts.selected_kind
    selected_source = facts.selected_source
    if forced_kind and selected_source != "terminal_blocked" and selected_kind and selected_kind != forced_kind:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "forced_selected_task_kind_mismatch",
            "`derive` must select the forced task kind emitted by the anti-loop chain-stall gate before choosing another goal-productive task.",
            {"selected_task_kind": selected_kind, "forced_selected_task_kind": forced_kind},
        )
    output_delta_status = str(
        first_present(
            result,
            [
                "output_delta_status",
                "output_delta.output_delta_status",
                "output_delta_gate.output_delta_status",
                "result.output_delta.output_delta_status",
            ],
        )
        or ""
    ).lower()
    produced_domain_delta = first_present(
        result,
        [
            "produced_domain_delta",
            "output_delta.produced_domain_delta",
            "output_delta_gate.produced_domain_delta",
            "result.output_delta.produced_domain_delta",
        ],
    )
    metadata_only = first_present(
        result,
        [
            "metadata_only",
            "output_delta.metadata_only",
            "output_delta_gate.metadata_only",
            "result.output_delta.metadata_only",
        ],
    )
    effective_progress_kind = str(
        first_present(
            result,
            [
                "effective_progress_kind",
                "output_delta.effective_progress_kind",
                "output_delta_gate.effective_progress_kind",
                "result.output_delta.effective_progress_kind",
            ],
        )
        or ""
    ).lower()
    facts.effective_progress_kind = effective_progress_kind
    facts.metadata_only = metadata_only
    facts.output_delta_status = output_delta_status
    facts.produced_domain_delta = produced_domain_delta


def _check_progress_policy_part_02(facts: DeriveFacts) -> None:
    result = facts.result
    changed_vs_previous = first_present(
        result,
        [
            "changed_vs_previous",
            "output_delta.changed_vs_previous",
            "output_delta_gate.changed_vs_previous",
            "result.output_delta.changed_vs_previous",
        ],
    )
    semantic_progress = first_present(
        result,
        [
            "semantic_progress",
            "output_delta.semantic_progress",
            "output_delta_gate.semantic_progress",
            "result.output_delta.semantic_progress",
        ],
    )
    measurement_progress_allowed = boolish(
        first_present(
            result,
            [
                "measurement_progress_allowed",
                "anti_loop_progress_gate.measurement_progress_allowed",
                "result.anti_loop_progress_gate.measurement_progress_allowed",
            ],
        )
    )
    measurement_progress = boolish(
        first_present(
            result,
            [
                "measurement_progress",
                "anti_loop_progress_gate.measurement_progress",
                "result.anti_loop_progress_gate.measurement_progress",
            ],
        )
    )
    substance_delta_pass = boolish(
        first_present(
            result,
            [
                "substance_delta_pass",
                "substance_delta_gate.substance_delta_pass",
                "anti_loop_progress_gate.substance_delta_gate.substance_delta_pass",
                "result.anti_loop_progress_gate.substance_delta_gate.substance_delta_pass",
            ],
        )
    )
    facts.changed_vs_previous = changed_vs_previous
    facts.measurement_progress = measurement_progress
    facts.measurement_progress_allowed = measurement_progress_allowed
    facts.semantic_progress = semantic_progress
    facts.substance_delta_pass = substance_delta_pass


def _check_progress_policy_part_03(facts: DeriveFacts) -> None:
    result = facts.result
    vacuous_corrective_noop = boolish(
        first_present(
            result,
            [
                "surface_corrective_noop",
                "vacuous_corrective_gate.surface_corrective_noop",
                "anti_loop_progress_gate.vacuous_corrective_gate.surface_corrective_noop",
                "result.anti_loop_progress_gate.vacuous_corrective_gate.surface_corrective_noop",
            ],
        )
    )
    advice_metrics_stale = boolish(
        first_present(
            result,
            [
                "advice_metrics_stale",
                "advice_freshness_gate.advice_metrics_stale",
                "anti_loop_progress_gate.advice_freshness_gate.advice_metrics_stale",
                "result.anti_loop_progress_gate.advice_freshness_gate.advice_metrics_stale",
            ],
        )
    )
    measurement_streak = number_value(
        first_present(
            result,
            [
                "measurement_streak",
                "anti_loop_progress_gate.measurement_streak",
                "result.anti_loop_progress_gate.measurement_streak",
            ],
        )
    )
    measurement_streak_cap = number_value(
        first_present(
            result,
            [
                "measurement_streak_cap",
                "anti_loop_progress_gate.measurement_streak_cap",
                "result.anti_loop_progress_gate.measurement_streak_cap",
            ],
        )
    )
    blocker_mutation_kind = str(
        first_present(
            result,
            [
                "blocker_mutation_kind",
                "anti_loop_progress_gate.blocker_mutation_kind",
                "result.anti_loop_progress_gate.blocker_mutation_kind",
            ],
        )
        or ""
    ).lower()
    forward_mutation_progress = blocker_mutation_kind == "forward_mutation"
    facts.advice_metrics_stale = advice_metrics_stale
    facts.blocker_mutation_kind = blocker_mutation_kind
    facts.forward_mutation_progress = forward_mutation_progress
    facts.measurement_streak = measurement_streak
    facts.measurement_streak_cap = measurement_streak_cap
    facts.vacuous_corrective_noop = vacuous_corrective_noop


def _check_progress_policy_part_04(facts: DeriveFacts) -> None:
    changed_vs_previous = facts.changed_vs_previous
    metadata_only = facts.metadata_only
    output_delta_status = facts.output_delta_status
    produced_domain_delta = facts.produced_domain_delta
    result = facts.result
    semantic_progress = facts.semantic_progress
    terminal_outcome_value = first_present(
        result,
        [
            "terminal_outcome_changed",
            "anti_loop_progress_gate.terminal_outcome_changed",
            "result.anti_loop_progress_gate.terminal_outcome_changed",
        ],
    )
    terminal_outcome_changed = (
        boolish(terminal_outcome_value)
        if terminal_outcome_value is not None
        else boolish(changed_vs_previous) and boolish(semantic_progress)
    )
    forward_mutation_vacuous = boolish(
        first_present(
            result,
            [
                "forward_mutation_vacuous",
                "anti_loop_progress_gate.forward_mutation_vacuous",
                "result.anti_loop_progress_gate.forward_mutation_vacuous",
            ],
        )
    )
    force_implementation_cycle = boolish(
        first_present(
            result,
            [
                "force_implementation_cycle",
                "anti_loop_progress_gate.force_implementation_cycle",
                "result.anti_loop_progress_gate.force_implementation_cycle",
            ],
        )
    )
    command_surface_class = str(
        first_present(
            result,
            [
                "command_surface_class",
                "selected_task.command_surface_class",
                "command_surface_budget.command_surface_class",
                "result.command_surface_class",
            ],
        )
        or ""
    ).strip().lower()
    allowed_force_impl_class = command_surface_class in {"b", "class_b", "c", "class_c"}
    output_delta_applies = output_delta_status == "complete" or produced_domain_delta is not None or metadata_only is not None
    facts.allowed_force_impl_class = allowed_force_impl_class
    facts.command_surface_class = command_surface_class
    facts.force_implementation_cycle = force_implementation_cycle
    facts.forward_mutation_vacuous = forward_mutation_vacuous
    facts.output_delta_applies = output_delta_applies
    facts.terminal_outcome_changed = terminal_outcome_changed


def _check_progress_policy_part_05(facts: DeriveFacts) -> None:
    blocker_mutation_kind = facts.blocker_mutation_kind
    changed_vs_previous = facts.changed_vs_previous
    effective_progress_kind = facts.effective_progress_kind
    findings = facts.findings
    forward_mutation_progress = facts.forward_mutation_progress
    forward_mutation_vacuous = facts.forward_mutation_vacuous
    measurement_progress = facts.measurement_progress
    measurement_progress_allowed = facts.measurement_progress_allowed
    metadata_only = facts.metadata_only
    mode = facts.mode
    output_delta_applies = facts.output_delta_applies
    output_delta_status = facts.output_delta_status
    produced_domain_delta = facts.produced_domain_delta
    progress_kind = facts.progress_kind
    semantic_progress = facts.semantic_progress
    substance_delta_pass = facts.substance_delta_pass
    terminal_outcome_changed = facts.terminal_outcome_changed
    vacuous_corrective_noop = facts.vacuous_corrective_noop
    if progress_kind == "goal_productive" and output_delta_applies and (
        boolish(metadata_only)
        or (produced_domain_delta is not None and not boolish(produced_domain_delta))
        or (produced_domain_delta is not None and boolish(produced_domain_delta) and not (boolish(changed_vs_previous) and boolish(semantic_progress)))
    ) and not (measurement_progress_allowed or forward_mutation_progress):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "goal_productive_without_output_delta",
            "`derive` cannot classify work as goal_productive without produced_domain_delta=true backed by changed_vs_previous=true and semantic_progress=true.",
            {
                "progress_kind": progress_kind,
                "effective_progress_kind": effective_progress_kind or None,
                "output_delta_status": output_delta_status or None,
                "produced_domain_delta": produced_domain_delta,
                "changed_vs_previous": changed_vs_previous,
                "semantic_progress": semantic_progress,
                "metadata_only": metadata_only,
            },
        )
    if progress_kind == "goal_productive" and (measurement_progress or blocker_mutation_kind == "forward_mutation") and not (substance_delta_pass or boolish(changed_vs_previous) and boolish(semantic_progress)):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "goal_productive_without_substance_delta",
            "`derive` cannot promote measurement or ladder-rung movement from tool/oracle existence alone; require G-SUBSTANCE pass or strict changed-and-semantic primary-output evidence.",
            {
                "measurement_progress": measurement_progress,
                "blocker_mutation_kind": blocker_mutation_kind or None,
                "substance_delta_pass": substance_delta_pass,
                "changed_vs_previous": changed_vs_previous,
                "semantic_progress": semantic_progress,
            },
        )
    if progress_kind == "goal_productive" and forward_mutation_progress and (forward_mutation_vacuous or not terminal_outcome_changed):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "goal_productive_forward_mutation_without_terminal_outcome_delta",
            "`derive` cannot promote capability-ladder forward mutation when the observed terminal outcome did not change.",
            {
                "blocker_mutation_kind": blocker_mutation_kind,
                "terminal_outcome_changed": terminal_outcome_changed,
                "forward_mutation_vacuous": forward_mutation_vacuous,
            },
        )
    if progress_kind == "goal_productive" and vacuous_corrective_noop and not (boolish(changed_vs_previous) and boolish(semantic_progress)):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "goal_productive_from_vacuous_corrective",
            "`derive` cannot count corrective/backfill rows as goal_productive when attempted lanes resolved zero items.",
        )


def _check_progress_policy_part_06(facts: DeriveFacts) -> None:
    advice_metrics_stale = facts.advice_metrics_stale
    allowed_force_impl_class = facts.allowed_force_impl_class
    command_surface_class = facts.command_surface_class
    findings = facts.findings
    force_implementation_cycle = facts.force_implementation_cycle
    measurement_streak = facts.measurement_streak
    measurement_streak_cap = facts.measurement_streak_cap
    mode = facts.mode
    progress_kind = facts.progress_kind
    result = facts.result
    selected_source = facts.selected_source
    if advice_metrics_stale and has_value(result, "used_advice") and not advice_handling_rationale_present(result):
        add(
            findings,
            "warn",
            "stale_advice_used_without_rationale",
            "`derive` used advice whose headline fingerprint/metric claims are stale without a defer/reject/refresh rationale.",
        )
    if measurement_streak is not None and measurement_streak_cap is not None and measurement_streak > measurement_streak_cap and selected_source != "terminal_blocked" and not has_value(result, "terminal_blocker"):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "measurement_streak_cap_exceeded",
            "Measurement progress exemption is capped; derive must not continue non-terminal measurement/governance work after the cap.",
            {"measurement_streak": measurement_streak, "measurement_streak_cap": measurement_streak_cap},
        )
    if force_implementation_cycle and not has_value(result, "terminal_blocker") and progress_kind != "goal_productive":
        add(
            findings,
            "block" if mode == "block" else "warn",
            "force_implementation_cycle_unhandled",
            "Forward-mutation budget is exhausted; derive must select implementation work or terminal/user escalation.",
            {"progress_kind": progress_kind or None},
        )
    if force_implementation_cycle and command_surface_class and not allowed_force_impl_class and not has_value(result, "terminal_blocker"):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "force_implementation_command_surface_class_blocked",
            "Forced implementation under command-surface pressure may use only Class B in-place expansion or Class C surface reduction.",
            {"command_surface_class": command_surface_class},
        )


def check_progress_policy(facts: DeriveFacts) -> None:
    _check_progress_policy_part_01(facts)
    _check_progress_policy_part_02(facts)
    _check_progress_policy_part_03(facts)
    _check_progress_policy_part_04(facts)
    _check_progress_policy_part_05(facts)
    _check_progress_policy_part_06(facts)

