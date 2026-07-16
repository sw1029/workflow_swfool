from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from .common import add, boolish, first_present
from .receipts import _declared_values, _full_sha256, _opaque_scalar, _opaque_string_items


@dataclass
class _ExpectationState:
    target: Any
    result: Any
    mode: Any
    findings: Any
    actual_evidence_missing: Any = None
    actual_value_mismatch: Any = None
    allowed_reviews: Any = None
    comparison: Any = None
    comparison_signatures: Any = None
    detected_mismatches: Any = None
    expectation_contract_invalid: Any = None
    expectation_declared: Any = None
    metadata_actual: Any = None
    producer_expected: Any = None
    repeated_miss: Any = None
    review: Any = None
    severity: Any = None
    status: Any = None
    transition_claimed: Any = None
    duplicate_result_conflict: bool = False
    halted: bool = False


def _validate_task_pack_expectation_comparison_part_01(state: _ExpectationState) -> None:
    mode = state.mode
    result = state.result
    target = state.target
    severity = "block" if mode == "block" or target in {"validate", "derive", "report"} else "warn"
    expectation_fields = (
        "progress_target",
        "progress_kind_expected",
        "semantic_signature_expected",
        "blocker_signature_expected",
        "required_output_classes",
    )
    expectation_declared = any(
        first_present(result, [field, f"task_pack_item.{field}"]) is not None
        for field in expectation_fields
    ) or first_present(result, ["adoption_axis_contract.required_output_classes", "task_pack_item.adoption_axis_contract.required_output_classes"]) is not None
    transition_claimed = any(
        boolish(first_present(result, [path]))
        for path in (
            "task_pack_auto_consume",
            "successor_auto_promoted",
            "pack_transition_applied",
            "result.pack_transition_applied",
            "task_pack_item.result.pack_transition_applied",
            "task_pack_result.pack_transition_applied",
            "result.task_pack_item.result.pack_transition_applied",
            "result.task_pack_result.pack_transition_applied",
        )
    )
    comparison_paths = (
        "expectation_comparison",
        "task_pack_item.result.expectation_comparison",
        "task_pack_result.expectation_comparison",
        "result.expectation_comparison",
        "result.task_pack_item.result.expectation_comparison",
        "result.task_pack_result.expectation_comparison",
    )
    comparison_values = _declared_values(result, comparison_paths)
    comparison = next((value for value in comparison_values if isinstance(value, dict)), None)
    comparison_signatures: set[tuple[Any, ...]] = set()
    for value in comparison_values:
        if not isinstance(value, dict):
            comparison_signatures.add(("invalid_contract",))
            continue
        raw_comparison_status = value.get("status")
        raw_comparison_review = value.get("remaining_pack_review")
        mismatch_items, mismatch_valid = _opaque_string_items(value.get("mismatched_axes"))
        comparison_signatures.add(
            (
                raw_comparison_status.strip().lower() if isinstance(raw_comparison_status, str) else "invalid_contract",
                raw_comparison_review.strip().lower() if isinstance(raw_comparison_review, str) else "invalid_contract",
                tuple(sorted(set(mismatch_items))),
                mismatch_valid,
            )
        )
    state.comparison = comparison
    state.comparison_signatures = comparison_signatures
    state.expectation_declared = expectation_declared
    state.severity = severity
    state.transition_claimed = transition_claimed


def _validate_task_pack_expectation_comparison_part_02(state: _ExpectationState) -> None:
    result = state.result
    duplicate_field_paths = {
        "progress_target_expected": (
            "progress_target",
            "task_pack_item.progress_target",
        ),
        "progress_verdict_actual": (
            "progress_verdict",
            "task_pack_item.result.progress_verdict",
            "task_pack_result.progress_verdict",
            "result.progress_verdict",
        ),
        "progress_kind_expected": (
            "progress_kind_expected",
            "task_pack_item.progress_kind_expected",
        ),
        "progress_kind_actual": (
            "progress_kind",
            "task_pack_item.result.progress_kind",
            "task_pack_result.progress_kind",
            "result.progress_kind",
            "result.task_pack_item.result.progress_kind",
        ),
        "semantic_signature_expected": (
            "semantic_signature_expected",
            "task_pack_item.semantic_signature_expected",
        ),
        "semantic_signature_actual": (
            "semantic_signature",
            "task_pack_item.result.semantic_signature",
            "task_pack_result.semantic_signature",
            "result.semantic_signature",
        ),
        "blocker_signature_expected": (
            "blocker_signature_expected",
            "task_pack_item.blocker_signature_expected",
        ),
        "blocker_signature_actual": (
            "blocker_signature",
            "task_pack_item.result.blocker_signature",
            "task_pack_result.blocker_signature",
            "result.blocker_signature",
        ),
    }
    duplicate_result_conflict = False
    for paths in duplicate_field_paths.values():
        values = _declared_values(result, paths)
        normalized = [value.strip() for value in values if _opaque_scalar(value)]
        if len(normalized) != len(values) or len(set(normalized)) > 1:
            duplicate_result_conflict = True
    state.duplicate_result_conflict = duplicate_result_conflict


def _validate_task_pack_expectation_comparison_part_03(state: _ExpectationState) -> None:
    comparison = state.comparison
    comparison_signatures = state.comparison_signatures
    expectation_declared = state.expectation_declared
    findings = state.findings
    result = state.result
    severity = state.severity
    transition_claimed = state.transition_claimed
    duplicate_result_conflict = state.duplicate_result_conflict
    for paths in (
        (
            "required_output_classes",
            "adoption_axis_contract.required_output_classes",
            "task_pack_item.adoption_axis_contract.required_output_classes",
        ),
        (
            "observed_output_classes",
            "result.observed_output_classes",
            "task_pack_item.result.observed_output_classes",
            "task_pack_result.observed_output_classes",
        ),
    ):
        values = _declared_values(result, paths)
        normalized_sets: set[tuple[str, ...]] = set()
        for value in values:
            items, valid = _opaque_string_items(value)
            if not valid:
                duplicate_result_conflict = True
            else:
                normalized_sets.add(tuple(sorted(set(items))))
        if len(normalized_sets) > 1:
            duplicate_result_conflict = True
    if len(comparison_signatures) > 1 or duplicate_result_conflict:
        add(
            findings,
            severity,
            "task_pack_expectation_surface_conflict",
            "Duplicate task-pack expectation/result surfaces must converge before the remaining pack can transition.",
        )
    if not isinstance(comparison, dict):
        if expectation_declared or transition_claimed:
            add(
                findings,
                severity,
                "task_pack_expectation_comparison_missing",
                "Declared task-pack expectations or a pack transition require an expectation comparison before the remaining pack is consumed.",
            )
        state.halted = True
        return
    raw_status = comparison.get("status")
    status = raw_status.strip().lower() if isinstance(raw_status, str) else ""
    allowed_statuses = {"match", "miss", "not_evaluated", "not_applicable"}
    allowed_reviews = {"continue", "reorder", "replace", "split", "pause", "terminal_candidate"}
    raw_review = comparison.get("remaining_pack_review")
    review = raw_review.strip().lower() if isinstance(raw_review, str) else ""
    if status not in allowed_statuses:
        add(findings, severity, "task_pack_expectation_status_invalid", "Task-pack expectation comparison status is invalid.")
        state.halted = True
        return
    state.allowed_reviews = allowed_reviews
    state.review = review
    state.status = status


def _validate_task_pack_expectation_comparison_part_04(state: _ExpectationState) -> None:
    if state.halted:
        return
    comparison = state.comparison
    findings = state.findings
    result = state.result
    severity = state.severity
    status = state.status
    expected_actual_pairs = (
        ("progress_target", "progress_verdict"),
        ("progress_kind_expected", "progress_kind"),
        ("semantic_signature_expected", "semantic_signature"),
        ("blocker_signature_expected", "blocker_signature"),
    )
    detected_mismatches: list[str] = []
    actual_evidence_missing = False
    expectation_contract_invalid = False
    for expected_field, actual_field in expected_actual_pairs:
        expected = first_present(result, [expected_field, f"task_pack_item.{expected_field}"])
        actual = first_present(result, [actual_field, f"task_pack_item.result.{actual_field}", f"result.{actual_field}"])
        if expected is not None:
            if not _opaque_scalar(expected):
                expectation_contract_invalid = True
            if actual is None:
                actual_evidence_missing = True
                detected_mismatches.append(f"{expected_field}:actual_missing")
            elif not _opaque_scalar(actual):
                expectation_contract_invalid = True
            elif _opaque_scalar(expected) and expected.strip() != actual.strip():
                detected_mismatches.append(f"{expected_field}:{actual_field}")
    required_output_value = first_present(result, ["required_output_classes", "adoption_axis_contract.required_output_classes", "task_pack_item.adoption_axis_contract.required_output_classes"])
    observed_output_value = first_present(result, ["observed_output_classes", "result.observed_output_classes", "task_pack_item.result.observed_output_classes"])
    required_output_items, required_outputs_valid = _opaque_string_items(required_output_value)
    observed_output_items, observed_outputs_valid = _opaque_string_items(observed_output_value)
    required_outputs = set(required_output_items)
    observed_outputs = set(observed_output_items)
    expectation_contract_invalid = expectation_contract_invalid or not required_outputs_valid or not observed_outputs_valid
    if required_outputs and not observed_outputs:
        actual_evidence_missing = True
    if required_outputs and not required_outputs <= observed_outputs:
        detected_mismatches.append("required_output_classes:observed_output_classes")
    declared_mismatches, mismatched_axes_valid = _opaque_string_items(comparison.get("mismatched_axes"))
    expectation_contract_invalid = expectation_contract_invalid or not mismatched_axes_valid
    if expectation_contract_invalid:
        add(
            findings,
            severity,
            "task_pack_expectation_contract_invalid",
            "Task-pack expectation comparison requires bounded opaque expected, actual, output-class, and mismatch-axis IDs.",
        )
    if status == "match" and (detected_mismatches or declared_mismatches):
        add(
            findings,
            severity,
            "task_pack_expectation_false_match",
            "Task-pack expectation comparison cannot report match when expected and actual fields diverge.",
            {"detected_mismatches": detected_mismatches, "declared_mismatches": declared_mismatches},
        )
    actual_value_mismatch = bool(detected_mismatches) and not actual_evidence_missing
    state.actual_evidence_missing = actual_evidence_missing
    state.actual_value_mismatch = actual_value_mismatch
    state.detected_mismatches = detected_mismatches
    state.expectation_contract_invalid = expectation_contract_invalid


def _validate_task_pack_expectation_comparison_part_05(state: _ExpectationState) -> None:
    if state.halted:
        return
    actual_evidence_missing = state.actual_evidence_missing
    actual_value_mismatch = state.actual_value_mismatch
    allowed_reviews = state.allowed_reviews
    detected_mismatches = state.detected_mismatches
    expectation_contract_invalid = state.expectation_contract_invalid
    expectation_declared = state.expectation_declared
    findings = state.findings
    result = state.result
    review = state.review
    severity = state.severity
    status = state.status
    transition_claimed = state.transition_claimed
    if expectation_declared and status == "not_applicable" or actual_value_mismatch and status != "miss":
        add(
            findings,
            severity,
            "task_pack_expectation_status_mismatch",
            "Declared and observable task-pack expectations cannot be bypassed with a non-miss comparison status.",
            {"detected_mismatch_fields": detected_mismatches},
        )
    if actual_evidence_missing and status != "not_evaluated":
        add(
            findings,
            severity,
            "task_pack_expectation_actual_missing_status",
            "Missing actual evidence requires expectation status not_evaluated before the remaining pack is reviewed.",
            {"detected_mismatches": detected_mismatches},
        )
    if status == "miss" and review not in allowed_reviews:
        add(findings, severity, "task_pack_expectation_miss_unreviewed", "Expectation miss requires an explicit review of the remaining pack.")
    if (
        status in {"miss", "not_evaluated"}
        or bool(detected_mismatches)
        or expectation_contract_invalid
    ) and transition_claimed:
        add(findings, severity, "task_pack_expectation_unresolved_transition", "An expectation miss or unevaluated comparison cannot auto-consume the remaining pack.")
    miss_streak = first_present(result, ["expectation_miss_streak", "task_pack_item.result.expectation_miss_streak"])
    miss_streak_cap = first_present(
        result,
        ["expectation_miss_streak_cap", "task_pack_item.expectation_miss_streak_cap"],
    )
    try:
        threshold_reached = (
            miss_streak is not None
            and miss_streak_cap is not None
            and int(miss_streak) >= max(1, int(miss_streak_cap))
        )
    except (TypeError, ValueError):
        threshold_reached = False
    repeated_miss = boolish(
        first_present(
            result,
            ["repeated_expectation_miss", "task_pack_item.result.repeated_expectation_miss"],
        )
    ) or threshold_reached
    producer_expected_value = first_present(result, ["progress_kind_expected", "task_pack_item.progress_kind_expected"])
    producer_expected = isinstance(producer_expected_value, str) and producer_expected_value.strip().lower() == "goal_productive"
    progress_kind_value = first_present(result, ["progress_kind", "result.progress_kind"])
    metadata_actual = boolish(first_present(result, ["metadata_only", "result.metadata_only"])) or (
        isinstance(progress_kind_value, str) and progress_kind_value.strip().lower() == "governance_only"
    )
    state.metadata_actual = metadata_actual
    state.producer_expected = producer_expected
    state.repeated_miss = repeated_miss


def _validate_task_pack_expectation_comparison_part_06(state: _ExpectationState) -> None:
    if state.halted:
        return
    findings = state.findings
    metadata_actual = state.metadata_actual
    producer_expected = state.producer_expected
    repeated_miss = state.repeated_miss
    review = state.review
    severity = state.severity
    status = state.status
    if status == "miss" and review == "continue" and producer_expected and metadata_actual and repeated_miss:
        add(
            findings,
            severity,
            "task_pack_repeated_metadata_miss_auto_continue",
            "Repeated metadata-only results against an expected producer output require pack reordering, replacement, split, pause, or terminal review before continue.",
        )


def validate_task_pack_expectation_comparison(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    state = _ExpectationState(target=target, result=result, mode=mode, findings=findings)
    _validate_task_pack_expectation_comparison_part_01(state)
    _validate_task_pack_expectation_comparison_part_02(state)
    _validate_task_pack_expectation_comparison_part_03(state)
    _validate_task_pack_expectation_comparison_part_04(state)
    _validate_task_pack_expectation_comparison_part_05(state)
    _validate_task_pack_expectation_comparison_part_06(state)


def validate_state_projection(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    severity = "block" if mode == "block" or target in {"validate", "derive", "report"} else "warn"
    projection_required = boolish(
        first_present(
            result,
            [
                "state_projection_required",
                "lifecycle_transition_result.state_projection_required",
                "result.state_projection_required",
            ],
        )
    )
    transition_trigger_fields = (
        "lifecycle_transition_applied",
        "authority_projection_applied",
        "task_projection_applied",
        "task_index_projection_applied",
        "state_projection_consumed",
        "successor_auto_promoted",
        "promotion_applied",
        "pack_transition_applied",
    )
    dependent_transition = projection_required or any(
        boolish(first_present(result, [field, f"lifecycle_transition_result.{field}", f"result.{field}"]))
        for field in transition_trigger_fields
    )
    projection = first_present(
        result,
        ["state_projection", "lifecycle_transition_result.state_projection", "result.state_projection"],
    )
    if not isinstance(projection, dict):
        if dependent_transition:
            add(
                findings,
                severity,
                "state_projection_missing",
                "A declared authority/task/index transition requires its state projection receipt.",
            )
        return
    status = str(projection.get("projection_status") or "").strip().lower()
    allowed = {"current", "stale_projection", "not_evaluated", "conflict"}
    if status not in allowed:
        add(findings, severity if dependent_transition else "warn", "state_projection_status_invalid", "State projection status is invalid.")
        return
    epoch_value = projection.get("projection_epoch")
    source_decision_value = projection.get("source_decision_id")
    epoch = epoch_value.strip() if _opaque_scalar(epoch_value) else ""
    source_decision_id = source_decision_value.strip() if _opaque_scalar(source_decision_value) else ""
    surface_epochs = projection.get("surface_epochs") if isinstance(projection.get("surface_epochs"), dict) else {}
    missing_current: list[str] = []
    if status == "current":
        if not epoch:
            missing_current.append("projection_epoch")
        if not source_decision_id:
            missing_current.append("source_decision_id")
        for surface in ("authority", "task", "index"):
            surface_epoch = surface_epochs.get(surface)
            if not _opaque_scalar(surface_epoch) or surface_epoch.strip() != epoch:
                missing_current.append(f"surface_epochs.{surface}")
        for digest_field in ("authority_digest", "task_digest", "index_digest"):
            if not _full_sha256(projection.get(digest_field)):
                missing_current.append(digest_field)
        if missing_current:
            add(
                findings,
                severity if dependent_transition else "warn",
                "state_projection_false_current",
                "A current state projection requires one source decision, one shared epoch, and valid authority/task/index digests.",
                {"invalid_fields": missing_current},
            )
    projection_not_current = status in {"stale_projection", "not_evaluated", "conflict"} or bool(missing_current)
    if projection_not_current and dependent_transition:
        add(
            findings,
            severity,
            "state_projection_not_current",
            "A stale, unevaluated, or conflicting authority/task/index projection cannot support transition, execution, close, or promotion.",
            {"projection_status": "false_current" if missing_current else status, "repair_first": bool(source_decision_id)},
        )
    if projection_not_current and dependent_transition and source_decision_id and boolish(result.get("user_input_required")):
        add(
            findings,
            severity,
            "state_projection_repair_precedes_user_reask",
            "The source decision is known; repair stale task/index projections before asking the user to repeat it.",
        )


