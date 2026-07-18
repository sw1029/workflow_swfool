from __future__ import annotations

from .shared import (
    CLASSIFICATION_REPAIR_TASK_KINDS,
    COLLECTION_CONSUMPTION_TASK_KINDS,
    CONTRACT_SATISFIABILITY_TASK_KINDS,
    ENVELOPE_THAW_TASK_KINDS,
    HARVEST_GATE_TASK_KINDS,
    INSTRUMENTATION_TASK_KINDS,
    REHARVEST_TASK_KINDS,
    add,
    boolish,
    first_present,
    list_values,
    non_empty,
    number_value,
    selected_disposition,
)
from .state import DeriveFacts


def _check_routing_outcomes_part_01(facts: DeriveFacts) -> None:
    findings = facts.findings
    harvest_gate_unaudited = facts.harvest_gate_unaudited
    harvest_preflight_required = facts.harvest_preflight_required
    mode = facts.mode
    result = facts.result
    selected_kind = facts.selected_kind
    terminal_selected = facts.terminal_selected
    harvest_risk_accepted = boolish(
        first_present(
            result,
            [
                "harvest_risk_accepted",
                "harvest_contract_preflight.harvest_risk_accepted",
                "harvest_contract_preflight_gate.harvest_risk_accepted",
                "anti_loop_progress_gate.harvest_risk_accepted",
                "result.harvest_contract_preflight_gate.harvest_risk_accepted",
            ],
        )
    )
    harvest_preflight_incompatible = any(
        boolish(
            first_present(
                result,
                [
                    field,
                    f"harvest_contract_preflight.{field}",
                    f"harvest_contract_preflight_gate.{field}",
                    f"anti_loop_progress_gate.{field}",
                    f"anti_loop_progress_gate.harvest_contract_preflight.{field}",
                    f"result.harvest_contract_preflight_gate.{field}",
                ],
            )
        )
        for field in ("lane_incompatible", "scale_incompatible", "contract_conflict")
    )
    if harvest_gate_unaudited and harvest_preflight_required and selected_kind in {"long_run_launch", "long_run_harvest"}:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_required_harvest_preflight_unaudited",
            "`derive` cannot silently select long-run launch/harvest when a required harvest preflight is unaudited; supply the inventory, record explicit risk acceptance, or choose terminal/user escalation.",
            {"selected_task_kind": selected_kind or None},
        )
    elif harvest_gate_unaudited:
        add(
            findings,
            "warn",
            "derive_harvest_gate_unaudited",
            "`harvest_gate_unaudited` is fail-quiet warning evidence; preserve it without inventing repository-specific harvest checks.",
        )
    if harvest_preflight_incompatible and not harvest_risk_accepted and not terminal_selected and selected_kind not in HARVEST_GATE_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_harvest_preflight_incompatible_unhandled",
            "`derive` must route non-degradable harvest-gate incompatibility to repair/mitigation before long-run launch unless `harvest_risk_accepted=true` is explicit.",
            {"selected_task_kind": selected_kind or None},
        )


def _check_routing_outcomes_part_02(facts: DeriveFacts) -> None:
    result = facts.result
    high_cost_artifact = boolish(
        first_present(
            result,
            [
                "high_cost_artifact",
                "disposal_proportionality_gate.high_cost_artifact",
                "run_disposition_gate.high_cost_artifact",
                "anti_loop_progress_gate.high_cost_artifact",
                "result.disposal_proportionality_gate.high_cost_artifact",
            ],
        )
    )
    destructive_disposition_requested = boolish(
        first_present(
            result,
            [
                "destructive_disposition_requested",
                "destructive_disposition",
                "disposal_proportionality_gate.destructive_disposition_requested",
                "run_disposition_gate.destructive_disposition_requested",
                "result.disposal_proportionality_gate.destructive_disposition_requested",
            ],
        )
    )
    destructive_disposition_blocked = boolish(
        first_present(
            result,
            [
                "destructive_disposition_blocked",
                "disposal_proportionality_gate.destructive_disposition_blocked",
                "anti_loop_progress_gate.destructive_disposition_blocked",
                "result.disposal_proportionality_gate.destructive_disposition_blocked",
            ],
        )
    )
    safety_violation = boolish(
        first_present(
            result,
            [
                "safety_violation",
                "safety_policy_violation",
                "disposal_proportionality_gate.safety_violation",
                "run_disposition_gate.safety_violation",
            ],
        )
    )
    facts.destructive_disposition_blocked = destructive_disposition_blocked
    facts.destructive_disposition_requested = destructive_disposition_requested
    facts.high_cost_artifact = high_cost_artifact
    facts.safety_violation = safety_violation


def _check_routing_outcomes_part_03(facts: DeriveFacts) -> None:
    destructive_disposition_blocked = facts.destructive_disposition_blocked
    destructive_disposition_requested = facts.destructive_disposition_requested
    findings = facts.findings
    high_cost_artifact = facts.high_cost_artifact
    mode = facts.mode
    result = facts.result
    safety_violation = facts.safety_violation
    selected_kind = facts.selected_kind
    terminal_selected = facts.terminal_selected
    reharvest_required = boolish(
        first_present(
            result,
            [
                "reharvest_before_rerun_required",
                "disposal_proportionality_gate.reharvest_before_rerun_required",
                "anti_loop_progress_gate.reharvest_before_rerun_required",
                "result.disposal_proportionality_gate.reharvest_before_rerun_required",
            ],
        )
    )
    rerun_before_reharvest = boolish(
        first_present(
            result,
            [
                "rerun_before_reharvest",
                "disposal_proportionality_gate.rerun_before_reharvest",
                "anti_loop_progress_gate.rerun_before_reharvest",
                "result.disposal_proportionality_gate.rerun_before_reharvest",
            ],
        )
    )
    destructive_high_cost = (destructive_disposition_blocked or (high_cost_artifact and destructive_disposition_requested)) and not safety_violation
    if (destructive_high_cost or reharvest_required or rerun_before_reharvest) and not terminal_selected and selected_kind not in REHARVEST_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_reharvest_or_quarantine_unhandled",
            "`derive` must preserve high-cost non-safety artifacts through quarantine and route available reharvest or gate repair before a new full rerun.",
            {"selected_task_kind": selected_kind or None},
        )
    mutually_unsatisfiable_contract = boolish(
        first_present(
            result,
            [
                "mutually_unsatisfiable_contract",
                "contract_satisfiability_gate.mutually_unsatisfiable_contract",
                "validation_predicate_contract.mutually_unsatisfiable_contract",
                "anti_loop_progress_gate.mutually_unsatisfiable_contract",
                "result.contract_satisfiability_gate.mutually_unsatisfiable_contract",
            ],
        )
    )
    if mutually_unsatisfiable_contract and not terminal_selected and selected_kind not in CONTRACT_SATISFIABILITY_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_mutually_unsatisfiable_contract_unhandled",
            "`derive` must reconcile predicate/directive contracts, preserve residual scope, terminal-block, or user-escalate before consuming either side as valid.",
            {"selected_task_kind": selected_kind or None},
        )


def _check_routing_outcomes_part_04(facts: DeriveFacts) -> None:
    findings = facts.findings
    mode = facts.mode
    result = facts.result
    selected_kind = facts.selected_kind
    terminal_selected = facts.terminal_selected
    sample_as_universe_misuse = boolish(
        first_present(
            result,
            [
                "sample_as_universe_misuse",
                "collection_consumption_gate.sample_as_universe_misuse",
                "closed_world_collection_consumption.sample_as_universe_misuse",
                "anti_loop_progress_gate.sample_as_universe_misuse",
                "result.collection_consumption_gate.sample_as_universe_misuse",
            ],
        )
    )
    if sample_as_universe_misuse and not terminal_selected and selected_kind not in COLLECTION_CONSUMPTION_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_sample_as_universe_misuse_unhandled",
            "`derive` must supply a full untruncated collection or revise the consumer to sample-only consistency before pass/close consumption.",
            {"selected_task_kind": selected_kind or None},
        )
    terminal_stage_contradiction = boolish(
        first_present(
            result,
            [
                "terminal_classification_stage_contradiction",
                "failure_surface_stage_gate.terminal_classification_stage_contradiction",
                "anti_loop_progress_gate.terminal_classification_stage_contradiction",
                "anti_loop_progress_gate.failure_surface_stage_gate.terminal_classification_stage_contradiction",
                "loopback_audit.terminal_classification_stage_contradiction",
                "result.anti_loop_progress_gate.terminal_classification_stage_contradiction",
            ],
        )
    )
    terminal_classification_invalid_for_counting = boolish(
        first_present(
            result,
            [
                "terminal_classification_invalid_for_counting",
                "failure_surface_stage_gate.terminal_classification_invalid_for_counting",
                "anti_loop_progress_gate.terminal_classification_invalid_for_counting",
                "result.anti_loop_progress_gate.terminal_classification_invalid_for_counting",
            ],
        )
    )
    facts.terminal_classification_invalid_for_counting = terminal_classification_invalid_for_counting
    facts.terminal_stage_contradiction = terminal_stage_contradiction


def _check_routing_outcomes_part_05(facts: DeriveFacts) -> None:
    result = facts.result
    same_input_contract_violation = boolish(
        first_present(
            result,
            [
                "same_input_contract_violation",
                "same_input_contract_gate.same_input_contract_violation",
                "anti_loop_progress_gate.same_input_contract_violation",
                "anti_loop_progress_gate.same_input_contract_gate.same_input_contract_violation",
                "result.anti_loop_progress_gate.same_input_contract_violation",
            ],
        )
    )
    instrumentation_supply_required = boolish(
        first_present(
            result,
            [
                "instrumentation_supply_required",
                "diagnostics_unavailable_gate.instrumentation_supply_required",
                "anti_loop_progress_gate.instrumentation_supply_required",
                "anti_loop_progress_gate.diagnostics_unavailable_gate.instrumentation_supply_required",
                "result.anti_loop_progress_gate.instrumentation_supply_required",
            ],
        )
    )
    diagnostics_unavailable_streak = number_value(
        first_present(
            result,
            [
                "diagnostics_unavailable_streak",
                "diagnostics_unavailable_gate.diagnostics_unavailable_streak",
                "anti_loop_progress_gate.diagnostics_unavailable_streak",
                "result.anti_loop_progress_gate.diagnostics_unavailable_streak",
            ],
        )
    )
    diagnostics_observable_without_new_instrumentation = boolish(
        first_present(
            result,
            [
                "diagnostics_observable_without_new_instrumentation",
                "success_failure_observable_without_instrumentation",
                "existing_diagnostics_sufficient",
                "hypothesis_repair_observability_rationale",
                "derive.diagnostics_observable_without_new_instrumentation",
                "result.existing_diagnostics_sufficient",
            ],
        )
    )
    facts.diagnostics_observable_without_new_instrumentation = diagnostics_observable_without_new_instrumentation
    facts.diagnostics_unavailable_streak = diagnostics_unavailable_streak
    facts.instrumentation_supply_required = instrumentation_supply_required
    facts.same_input_contract_violation = same_input_contract_violation


def _check_routing_outcomes_part_06(facts: DeriveFacts) -> None:
    result = facts.result
    independent_source_status = str(
        first_present(
            result,
            [
                "independent_source_separation_status",
                "verification_source_separation_gate.independent_source_separation_status",
                "evidence_provenance_gate.independent_source_separation_status",
                "anti_loop_progress_gate.independent_source_separation_status",
                "anti_loop_progress_gate.verification_source_separation_gate.independent_source_separation_status",
                "result.anti_loop_progress_gate.independent_source_separation_status",
            ],
        )
        or ""
    ).lower()
    independent_invariant_status = str(
        first_present(
            result,
            [
                "independent_invariant_separation_status",
                "verification_source_separation_gate.independent_invariant_separation_status",
                "evidence_provenance_gate.independent_invariant_separation_status",
                "anti_loop_progress_gate.independent_invariant_separation_status",
                "anti_loop_progress_gate.verification_source_separation_gate.independent_invariant_separation_status",
                "result.anti_loop_progress_gate.independent_invariant_separation_status",
            ],
        )
        or ""
    ).lower()
    independently_verified_downgraded_fields = list_values(
        first_present(
            result,
            [
                "independently_verified_downgraded_fields",
                "verification_source_separation_gate.independently_verified_downgraded_fields",
                "evidence_provenance_gate.independently_verified_downgraded_fields",
                "anti_loop_progress_gate.independently_verified_downgraded_fields",
                "result.anti_loop_progress_gate.independently_verified_downgraded_fields",
            ],
        )
    )
    envelope_thaw_item_required = boolish(
        first_present(
            result,
            [
                "envelope_thaw_item_required",
                "acceptance_reachability_gate.envelope_thaw_item_required",
                "anti_loop_progress_gate.envelope_thaw_item_required",
                "anti_loop_progress_gate.acceptance_reachability_gate.envelope_thaw_item_required",
                "result.anti_loop_progress_gate.envelope_thaw_item_required",
            ],
        )
    )
    envelope_thaw_item = first_present(
        result,
        [
            "envelope_thaw_item",
            "acceptance_reachability_gate.envelope_thaw_item",
            "anti_loop_progress_gate.envelope_thaw_item",
            "anti_loop_progress_gate.acceptance_reachability_gate.envelope_thaw_item",
            "selected_task.envelope_thaw_item",
            "result.anti_loop_progress_gate.envelope_thaw_item",
        ],
    )
    facts.envelope_thaw_item = envelope_thaw_item
    facts.envelope_thaw_item_required = envelope_thaw_item_required
    facts.independent_source_status = independent_source_status
    facts.independent_invariant_status = independent_invariant_status
    facts.independently_verified_downgraded_fields = independently_verified_downgraded_fields


def _check_routing_outcomes_part_07(facts: DeriveFacts) -> None:
    allowed_task_kinds = facts.allowed_task_kinds
    diagnostics_observable_without_new_instrumentation = facts.diagnostics_observable_without_new_instrumentation
    diagnostics_unavailable_streak = facts.diagnostics_unavailable_streak
    findings = facts.findings
    independent_source_status = facts.independent_source_status
    independent_invariant_status = facts.independent_invariant_status
    instrumentation_supply_required = facts.instrumentation_supply_required
    mode = facts.mode
    progress_kind = facts.progress_kind
    result = facts.result
    same_input_contract_violation = facts.same_input_contract_violation
    selected_kind = facts.selected_kind
    selected_source = facts.selected_source
    terminal_classification_invalid_for_counting = facts.terminal_classification_invalid_for_counting
    terminal_selected = facts.terminal_selected
    terminal_stage_contradiction = facts.terminal_stage_contradiction
    if progress_kind == "goal_productive" and allowed_task_kinds and selected_source != "terminal_blocked":
        if not selected_kind:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "selected_task_kind_missing_for_constrained_goal_productive",
                "`derive` must provide `selected_task_kind` when active gates restrict goal_productive to specific task kinds.",
                {"allowed_task_kinds": sorted(allowed_task_kinds)},
            )
        elif selected_kind not in allowed_task_kinds:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_productive_task_kind_not_allowed",
                "`derive` selected goal_productive by label but the task kind is outside the gate-constrained allowed set.",
                {"selected_task_kind": selected_kind, "allowed_task_kinds": sorted(allowed_task_kinds)},
            )
    classification_repair_selected = selected_kind in CLASSIFICATION_REPAIR_TASK_KINDS or selected_disposition(result, selected_source, progress_kind) in {
        "classification_stage_repair",
        "input_contract_repair",
    }
    if (terminal_stage_contradiction or terminal_classification_invalid_for_counting) and not terminal_selected and not classification_repair_selected:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_terminal_classification_stage_repair_missing",
            "`derive` cannot count or close a contradictory terminal classification; select a classification-stage repair/input-contract repair, terminal block, or user escalation.",
        )
    if same_input_contract_violation and not terminal_selected and not classification_repair_selected:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_same_input_contract_repair_missing",
            "`derive` cannot compare same-family failures across mismatched input sets; select same-input contract repair before counting progress.",
        )
    if instrumentation_supply_required and not terminal_selected and selected_kind not in INSTRUMENTATION_TASK_KINDS and not diagnostics_observable_without_new_instrumentation:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_missing_instrumentation_supply",
            "`derive` must enumerate/select instrumentation supply after repeated diagnostics_unavailable, or record why success/failure is already observable without new instrumentation.",
            {"diagnostics_unavailable_streak": diagnostics_unavailable_streak},
        )
    if progress_kind == "goal_productive" and independent_source_status in {"missing", "overlap", "blocked"} and not terminal_selected:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_productive_from_non_disjoint_independent_verification",
            "`derive` cannot treat independently_verified evidence as goal_productive when verification inputs overlap verified artifacts or are missing; consume it as attested or repair the source separation.",
            {"independent_source_separation_status": independent_source_status},
        )
    if progress_kind == "goal_productive" and independent_invariant_status in {"coupled", "unknown", "blocked"} and not terminal_selected:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_productive_from_coupled_invariant_verification",
            "`derive` cannot treat evidence as goal_productive when decisive invariant ownership is coupled or unknown.",
            {"independent_invariant_separation_status": independent_invariant_status},
        )


def _check_routing_outcomes_part_08(facts: DeriveFacts) -> None:
    envelope_thaw_item = facts.envelope_thaw_item
    envelope_thaw_item_required = facts.envelope_thaw_item_required
    findings = facts.findings
    independently_verified_downgraded_fields = facts.independently_verified_downgraded_fields
    mode = facts.mode
    progress_kind = facts.progress_kind
    selected_kind = facts.selected_kind
    terminal_selected = facts.terminal_selected
    if progress_kind == "goal_productive" and independently_verified_downgraded_fields and not terminal_selected:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_productive_from_downgraded_independent_verification",
            "`derive` cannot use auto-downgraded independently_verified fields as progress without new disjoint verification input.",
            {"downgraded_fields": independently_verified_downgraded_fields},
        )
    if envelope_thaw_item_required and not terminal_selected and selected_kind not in ENVELOPE_THAW_TASK_KINDS and not non_empty(envelope_thaw_item):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_envelope_thaw_item_missing",
            "`derive` must reserve an envelope_thaw_item when acceptance is unreachable under a frozen envelope, before ordinary repair continues.",
        )


def check_routing_outcomes(facts: DeriveFacts) -> None:
    _check_routing_outcomes_part_01(facts)
    _check_routing_outcomes_part_02(facts)
    _check_routing_outcomes_part_03(facts)
    _check_routing_outcomes_part_04(facts)
    _check_routing_outcomes_part_05(facts)
    _check_routing_outcomes_part_06(facts)
    _check_routing_outcomes_part_07(facts)
    _check_routing_outcomes_part_08(facts)
