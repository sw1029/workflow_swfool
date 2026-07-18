"""Validate scoped-progress claims without becoming another truth owner."""

from __future__ import annotations

from typing import Any, Iterable

from .accessors import boolish, first_present
from .scoped_progress import (
    Emit,
    PROGRESS_CLASSES,
    ScopedProgressAssessment,
    _declared,
    _mapping,
    _text,
    assess_scoped_progress,
)


def _enum_errors(
    mapping: dict[str, Any], fields: dict[str, Iterable[str]]
) -> list[str]:
    return [
        field
        for field, allowed in fields.items()
        if _text(mapping.get(field)) not in set(allowed)
    ]


def _validate_identity_shape(result: dict[str, Any], emit: Emit) -> None:
    contract_paths = (
        "progress_scope_contract",
        "scoped_progress.progress_scope_contract",
    )
    contract = _mapping(result, *contract_paths)
    scoped_observation_declared = _declared(
        result,
        "work_intent",
        "scoped_progress.work_intent",
        "progress_observations",
        "scoped_progress.progress_observations",
    )
    if not _declared(result, *contract_paths):
        if scoped_observation_declared:
            emit(
                "scoped_progress_identity_missing",
                "Scoped work intent and observations require a stable task/root/global identity contract.",
                None,
            )
        return
    required_ids = (
        "task_family_id",
        "root_family_id",
        "task_terminal_predicate_id",
        "root_terminal_predicate_id",
        "identity_basis_id",
    )
    invalid = [
        field for field in required_ids if not str(contract.get(field) or "").strip()
    ]
    applicability = _text(contract.get("global_scope_applicability"))
    if applicability not in {"applicable", "not_applicable"}:
        invalid.append("global_scope_applicability")
    global_fields = ("global_goal_axis_id", "global_terminal_predicate_id")
    if applicability == "applicable" and not all(
        str(contract.get(field) or "").strip() for field in global_fields
    ):
        invalid.extend(global_fields)
    if applicability == "not_applicable" and any(
        contract.get(field) not in {None, ""} for field in global_fields
    ):
        invalid.extend(global_fields)
    if invalid:
        emit(
            "scoped_progress_contract_malformed",
            "Scoped progress identity and global applicability must be explicit and internally consistent.",
            {"invalid_fields": sorted(set(invalid))},
        )


def _validate_projection_shape(result: dict[str, Any], emit: Emit) -> None:
    intent = _mapping(result, "work_intent", "scoped_progress.work_intent")
    if _declared(result, "work_intent", "scoped_progress.work_intent"):
        invalid = _enum_errors(
            intent,
            {
                "expected_scope": {"task", "root", "global"},
                "expected_progress_cap": PROGRESS_CLASSES,
            },
        )
        if not str(intent.get("selected_transition_kind") or "").strip():
            invalid.append("selected_transition_kind")
        if invalid:
            emit(
                "scoped_progress_intent_malformed",
                "Prospective work intent must preserve a transition kind, scope, and bounded progress cap.",
                {"invalid_fields": sorted(set(invalid))},
            )
    observations = _mapping(
        result, "progress_observations", "scoped_progress.progress_observations"
    )
    if _declared(
        result,
        "progress_observations",
        "scoped_progress.progress_observations",
    ):
        invalid = [
            f"{scope_name}.progress_class"
            for scope_name in ("task_scope", "root_scope", "global_scope")
            if not isinstance(observations.get(scope_name), dict)
            or _text(observations[scope_name].get("progress_class"))
            not in PROGRESS_CLASSES
        ]
        if invalid:
            emit(
                "scoped_progress_observations_malformed",
                "Task, root, and global observations must remain separate and use bounded progress classes.",
                {"invalid_fields": invalid},
            )
    closeout = _mapping(
        result, "closeout_projection", "scoped_progress.closeout_projection"
    )
    if _declared(result, "closeout_projection", "scoped_progress.closeout_projection"):
        invalid = _enum_errors(
            closeout,
            {
                "task_acceptance": {"pass", "fail", "partial", "not_evaluated"},
                "review_axis": {"pass", "fail", "unavailable", "not_applicable"},
                "global_readiness": {"ready", "blocked", "not_evaluated"},
                "task_lifecycle": {"active", "completed_local", "replaced"},
                "successor_state": {
                    "derived",
                    "terminal_wait",
                    "blocked_on_material_input",
                    "not_evaluated",
                },
            },
        )
        if invalid:
            emit(
                "scoped_progress_closeout_malformed",
                "Closeout must preserve task acceptance, review, readiness, lifecycle, and successor as separate axes.",
                {"invalid_fields": invalid},
            )


def _validate_classification(
    result: dict[str, Any],
    assessment: ScopedProgressAssessment,
    emit: Emit,
) -> None:
    retained = assessment.retained_change
    if retained.invalid_evidence_fields:
        emit(
            "retained_change_evidence_malformed",
            "Retained-change files and role digests must be typed exact evidence.",
            {"invalid_fields": list(retained.invalid_evidence_fields)},
        )
    classification = _mapping(
        result,
        "retained_change_classification",
        "scoped_progress.retained_change_classification",
    )
    if not _declared(
        result,
        "retained_change_classification",
        "scoped_progress.retained_change_classification",
    ):
        return
    boolean_fields = (
        "producer_body_changed",
        "producer_source_changed",
        "semantic_logic_changed",
        "tests_only_changed",
        "schema_or_verifier_only_changed",
        "lifecycle_only_changed",
    )
    invalid = [
        field
        for field in boolean_fields
        if not isinstance(classification.get(field), bool)
    ]
    if _text(classification.get("effective_progress_class")) not in PROGRESS_CLASSES:
        invalid.append("effective_progress_class")
    if invalid:
        emit(
            "retained_change_classification_malformed",
            "Retained-change classification requires six booleans and one bounded effective progress class.",
            {"invalid_fields": invalid},
        )
    expected: dict[str, Any] = {
        "producer_body_changed": retained.producer_body_changed,
        "producer_source_changed": retained.producer_source_changed,
        "semantic_logic_changed": retained.semantic_logic_changed,
        "tests_only_changed": retained.tests_only_changed,
        "schema_or_verifier_only_changed": retained.schema_or_verifier_only_changed,
        "lifecycle_only_changed": retained.lifecycle_only_changed,
        "effective_progress_class": assessment.effective_progress_class,
    }
    mismatches = {
        field: {"claimed": classification.get(field), "derived": derived}
        for field, derived in expected.items()
        if (
            _text(classification.get(field)) != derived
            if field == "effective_progress_class"
            else classification.get(field) is not derived
        )
    }
    if not retained.evaluated:
        emit(
            "retained_change_evidence_missing",
            "Retained-change classification cannot come from a task or message label without actual changed-file or digest evidence.",
            None,
        )
    if mismatches:
        emit(
            "retained_change_classification_mismatch",
            "Retained-change classification must match actual preserved change evidence and retrospective scoped progress.",
            {"mismatches": mismatches},
        )


def _validate_scope_claims(
    result: dict[str, Any],
    assessment: ScopedProgressAssessment,
    emit: Emit,
) -> None:
    observations = _mapping(
        result, "progress_observations", "scoped_progress.progress_observations"
    )
    root_scope = observations.get("root_scope", {})
    global_scope = observations.get("global_scope", {})
    if (
        isinstance(root_scope, dict)
        and _text(root_scope.get("progress_class")) == "root_reduction"
        and not assessment.root_reset_allowed
    ):
        emit(
            "root_progress_without_verified_residual_reduction",
            "Root reduction requires comparable same-basis improvement, residual reduction, and independent or explicit self-grounded verification.",
            None,
        )
    if (
        isinstance(global_scope, dict)
        and _text(global_scope.get("progress_class")) == "semantic"
        and not assessment.global_reset_allowed
    ):
        emit(
            "global_progress_without_exact_axis_complete_high_water",
            "Global semantic progress requires applicable exact-bound independently verified high-water movement across every active goal axis.",
            {"global_axes_complete": assessment.global_axes_complete},
        )
    intent = _mapping(result, "work_intent", "scoped_progress.work_intent")
    expected_cap = _text(intent.get("expected_progress_cap"))
    allowed_by_cap = {
        "semantic": PROGRESS_CLASSES,
        "root_reduction": {
            "root_reduction",
            "task_local",
            "safety",
            "governance",
            "none",
        },
        "task_local": {"task_local", "safety", "governance", "none"},
        "safety": {"safety", "none"},
        "governance": {"governance", "none"},
        "none": {"none"},
    }
    if (
        expected_cap in allowed_by_cap
        and assessment.effective_progress_class not in allowed_by_cap[expected_cap]
    ):
        emit(
            "retrospective_progress_exceeds_selected_cap",
            "Retrospective progress cannot exceed the prospective selection cap.",
            {
                "expected_progress_cap": expected_cap,
                "effective_progress_class": assessment.effective_progress_class,
            },
        )


def _validate_lifecycle(
    result: dict[str, Any],
    assessment: ScopedProgressAssessment,
    emit: Emit,
) -> None:
    closeout = _mapping(
        result, "closeout_projection", "scoped_progress.closeout_projection"
    )
    if _text(closeout.get("task_lifecycle")) == "completed_local":
        if _text(closeout.get("task_acceptance")) != "pass":
            emit(
                "completed_local_without_task_acceptance",
                "An immutable completed-local lifecycle requires bounded task acceptance pass.",
                None,
            )
        if _text(closeout.get("successor_state")) == "not_evaluated":
            emit(
                "completed_local_successor_not_evaluated",
                "Completed-local closeout must derive, wait, or identify a material-input blocker.",
                None,
            )
        if boolish(
            first_present(
                result,
                ("current_task_executable", "task_state.current_task_executable"),
            )
        ):
            emit(
                "completed_local_reactivated_as_executable",
                "A completed-local task is immutable history and cannot become executable again.",
                None,
            )
    if (
        _text(closeout.get("global_readiness")) == "ready"
        and not assessment.global_axes_complete
    ):
        emit(
            "scoped_global_readiness_overclaimed",
            "Global readiness cannot be ready while active axes are incomplete, unobserved, or conflicted.",
            None,
        )


def _reset_claim(result: dict[str, Any], scope: str) -> bool:
    return boolish(
        first_present(
            result,
            (
                f"{scope}_stall_reset",
                f"{scope}_scope_stall_reset",
                f"progress_observations.{scope}_scope.stall_reset",
                f"scoped_progress.progress_observations.{scope}_scope.stall_reset",
            ),
        )
    )


def _validate_resets(
    result: dict[str, Any],
    assessment: ScopedProgressAssessment,
    emit: Emit,
) -> None:
    if _reset_claim(result, "root") and not assessment.root_reset_allowed:
        emit(
            "task_local_progress_reset_root_stall",
            "Task-local, safety, governance, basis-changed, or unverified movement cannot reset stable-root stall.",
            {"effective_progress_class": assessment.effective_progress_class},
        )
    if _reset_claim(result, "global") and not assessment.global_reset_allowed:
        emit(
            "nonglobal_progress_reset_global_stall",
            "Only exact-bound independently verified global high-water movement may reset applicable global stall.",
            {"effective_progress_class": assessment.effective_progress_class},
        )


def _validate_target_claims(
    result: dict[str, Any],
    target: str,
    assessment: ScopedProgressAssessment,
    emit: Emit,
) -> None:
    if (
        target == "validate"
        and _text(result.get("progress_verdict")) == "advanced"
        and not assessment.global_reset_allowed
    ):
        emit(
            "validate_advanced_from_capped_scoped_progress",
            "Completion cannot upgrade bounded, root-only, incomplete, or conflicting observations to advanced global progress.",
            {"effective_progress_class": assessment.effective_progress_class},
        )
    semantic_progress = boolish(
        first_present(
            result,
            ("semantic_progress", "anti_loop_progress_gate.semantic_progress"),
        )
    )
    if (
        target == "loopback_audit"
        and semantic_progress
        and not assessment.global_reset_allowed
    ):
        emit(
            "loopback_semantic_progress_exceeds_scoped_evidence",
            "Loopback semantic progress needs exact axis-complete global evidence, not intent or bounded retained changes.",
            {"effective_progress_class": assessment.effective_progress_class},
        )
    effective_kind = _text(
        first_present(
            result,
            ("effective_progress_kind", "output_delta.effective_progress_kind"),
        )
    )
    if (
        target == "derive"
        and effective_kind in {"goal_productive", "global_semantic", "semantic"}
        and not assessment.global_reset_allowed
    ):
        emit(
            "derive_retrospective_progress_exceeds_scoped_evidence",
            "Derive may keep future goal intent, but retrospective progress must respect finalized scoped evidence.",
            {"effective_progress_class": assessment.effective_progress_class},
        )


def validate_scoped_progress(
    result: dict[str, Any],
    target: str,
    emit: Emit,
) -> ScopedProgressAssessment:
    assessment = assess_scoped_progress(result)
    if not assessment.present:
        return assessment
    _validate_identity_shape(result, emit)
    _validate_projection_shape(result, emit)
    _validate_classification(result, assessment, emit)
    _validate_scope_claims(result, assessment, emit)
    _validate_lifecycle(result, assessment, emit)
    _validate_resets(result, assessment, emit)
    _validate_target_claims(result, target, assessment, emit)
    return assessment
