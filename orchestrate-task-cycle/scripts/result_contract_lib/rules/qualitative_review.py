from __future__ import annotations

import math

from ..base import RuleContext, TargetContractRule
from ..common import add, boolish, first_present, has_value, list_values, non_empty, value_for


def _nonzero_scalar(value: object) -> bool:
    if isinstance(value, dict):
        return any(_nonzero_scalar(child) for child in value.values())
    if isinstance(value, list):
        return any(_nonzero_scalar(child) for child in value)
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0


def _finite_nonnegative_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value)) and value >= 0
    except (OverflowError, TypeError, ValueError):
        return False


def _scalar_counts_valid(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    for child in value.values():
        if isinstance(child, dict):
            if not _scalar_counts_valid(child):
                return False
        elif not _finite_nonnegative_number(child):
            return False
    return True


def _opaque_id(value: object, *, max_length: int = 256) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        return None
    if not normalized[0].isascii() or not normalized[0].isalnum() or any(
        not character.isascii() or not (character.isalnum() or character in "._-")
        for character in normalized
    ):
        return None
    return normalized


class QualitativeReviewRule(TargetContractRule):
    """Validate independent qualitative-review evidence and routing."""

    targets = frozenset({'qualitative_review'})

    def check(self, context: RuleContext) -> None:
        result = context.result
        mode = context.mode
        findings = context.findings
        review_agent_count = value_for(result, "review_agent_count")
        try:
            reviewer_count_value = int(str(review_agent_count))
        except (TypeError, ValueError):
            reviewer_count_value = None
        review_status = str(value_for(result, "review_status") or value_for(result, "status") or "").lower()
        quality_verdict = str(value_for(result, "quality_verdict") or "").lower()
        delegation_unavailable_reason = first_present(
            result,
            [
                "reviewer_delegation_unavailable_reason",
                "delegation_unavailable_reason",
                "review_delegation_unavailable_reason",
                "quality_review.reviewer_delegation_unavailable_reason",
                "qualitative_review.reviewer_delegation_unavailable_reason",
            ],
        )
        delegation_unavailable = delegation_unavailable_reason is not None
        review_na_reason = first_present(
            result,
            [
                "reason",
                "review_skipped_reason",
                "qualitative_review_pending_reason",
                "reviewer_delegation_unavailable_reason",
                "blockers",
            ],
        )
        reasoned_no_review = review_status in {"blocked", "not_applicable"} and non_empty(review_na_reason)
        if reviewer_count_value != 1 and not (reviewer_count_value == 0 and reasoned_no_review):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_agent_count_invalid",
                "`qualitative_review` must report exactly one reviewer agent.",
                {"review_agent_count": review_agent_count},
            )
        if review_status and review_status not in {"complete", "partial", "blocked", "not_applicable"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_status_invalid",
                "`qualitative_review` review_status should be complete, partial, blocked, or not_applicable.",
                {"review_status": review_status},
            )
        if quality_verdict and quality_verdict not in {"acceptable", "candidate_only", "quality_blocked", "unreviewable", "not_applicable"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_quality_verdict_invalid",
                "`qualitative_review` quality_verdict should use the owner skill vocabulary.",
                {"quality_verdict": quality_verdict},
            )
        direct_read_scope = {
            str(item).strip().lower()
            for item in list_values(
                first_present(
                    result,
                    [
                        "direct_read_scope",
                        "quality_review.direct_read_scope",
                        "qualitative_review.direct_read_scope",
                        "result.direct_read_scope",
                    ],
                )
            )
            if str(item).strip()
        }
        task_change_observed = "task_change" in direct_read_scope
        artifact_body_observed = "artifact_body" in direct_read_scope
        semantic_ready = str(first_present(result, ["semantic_ready", "quality_review.semantic_ready"]) or "").strip().lower()
        effective_progress_kind = str(
            first_present(result, ["effective_progress_kind", "progress_kind", "quality_review.effective_progress_kind"])
            or ""
        ).strip().lower()
        progress_cap = str(first_present(result, ["progress_cap", "quality_review.progress_cap"]) or "").strip().lower()
        semantic_axis_values = [
            first_present(
                result,
                [
                    "artifact_semantic_verdict",
                    "verdict_axes.artifact_semantic_verdict",
                    "result.artifact_semantic_verdict",
                    "result.verdict_axes.artifact_semantic_verdict",
                ],
            ),
            first_present(
                result,
                [
                    "goal_readiness_verdict",
                    "verdict_axes.goal_readiness_verdict",
                    "result.goal_readiness_verdict",
                    "result.verdict_axes.goal_readiness_verdict",
                ],
            ),
        ]

        def axis_pass(value: object) -> bool:
            raw = value.get("status") or value.get("verdict") if isinstance(value, dict) else value
            return str(raw or "").strip().lower() == "pass"

        semantic_positive = bool(
            boolish(first_present(result, ["semantic_progress", "observed_semantic_progress"]))
            or semantic_ready == "true"
            or effective_progress_kind == "goal_productive"
            or progress_cap == "goal_productive"
            or any(axis_pass(value) for value in semantic_axis_values)
        )
        truth_basis = str(
            first_present(
                result,
                [
                    "truth_basis",
                    "actual_body_truth_basis",
                    "actual_artifact_truth.truth_basis",
                    "quality_review.truth_basis",
                ],
            )
            or ""
        ).strip().lower()
        if review_status == "complete" and not (task_change_observed or artifact_body_observed):
            add(
                findings,
                (
                    "block"
                    if mode == "block" or quality_verdict == "acceptable"
                    else "warn"
                ),
                "qualitative_review_scope_not_evaluated",
                "A complete qualitative review must declare task_change, artifact_body, or both in direct_read_scope.",
            )
        if semantic_positive and (
            not artifact_body_observed
            or truth_basis in {"", "not_evaluated", "missing", "unknown"}
        ):
            add(
                findings,
                "block",
                "qualitative_review_artifact_body_not_evaluated",
                "Task-change or compatibility inspection cannot produce an artifact-body semantic pass; read the current body and preserve an evaluated truth basis.",
                {
                    "task_change_observed": task_change_observed,
                    "artifact_body_observed": artifact_body_observed,
                    "truth_basis": truth_basis or "not_evaluated",
                },
            )
        pass_with_unobserved_axes = boolish(
            first_present(
                result,
                [
                    "pass_with_unobserved_axes",
                    "goal_axis_completeness_gate.pass_with_unobserved_axes",
                    "quality_review.pass_with_unobserved_axes",
                    "qualitative_review.pass_with_unobserved_axes",
                    "result.goal_axis_completeness_gate.pass_with_unobserved_axes",
                ],
            )
        )
        unobserved_goal_axes = first_present(
            result,
            [
                "unobserved_goal_axes",
                "goal_axis_completeness_gate.unobserved_goal_axes",
                "quality_review.unobserved_goal_axes",
                "qualitative_review.unobserved_goal_axes",
                "result.goal_axis_completeness_gate.unobserved_goal_axes",
            ],
        )
        if (pass_with_unobserved_axes or non_empty(unobserved_goal_axes)) and quality_verdict == "acceptable":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_unobserved_axes_acceptable",
                "`qualitative_review` cannot report an acceptable pass for measurable goals with zero mapped observing axes; use pass_with_unobserved_axes and preserve axis-supply or residual work.",
                {"unobserved_goal_axes": unobserved_goal_axes or None},
            )
        reviewer_identity = str(
            first_present(
                result,
                [
                    "reviewer_agent",
                    "reviewer_id",
                    "reviewer_identity",
                    "reviewer",
                    "quality_review.reviewer_agent",
                    "quality_review.reviewer_id",
                    "quality_review.reviewer_identity",
                    "qualitative_review.reviewer_agent",
                    "qualitative_review.reviewer_id",
                    "qualitative_review.reviewer_identity",
                ],
            )
            or ""
        ).lower()
        main_reviewer_markers = ("main_orchestrator", "main_coordinator", "main coordinator", "orchestrator", "coordinator")
        if reviewer_identity and any(marker in reviewer_identity for marker in main_reviewer_markers):
            add(
                findings,
                "block",
                "qualitative_review_main_coordinator_substitution",
                "`qualitative_review` may not satisfy the reviewer-agent contract by naming the main coordinator as the reviewer.",
                {"reviewer_identity": reviewer_identity},
            )
        if delegation_unavailable and review_status == "complete":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_delegation_unavailable_marked_complete",
                "Reviewer delegation unavailability must be reported as blocked, partial, or not_applicable, not complete.",
                {"reviewer_delegation_unavailable_reason": delegation_unavailable_reason},
            )
        if review_status in {"blocked", "not_applicable"} and not (
            delegation_unavailable
            or non_empty(result.get("reason"))
            or has_value(result, "review_skipped_reason")
            or has_value(result, "qualitative_review_pending_reason")
            or has_value(result, "blockers")
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_blocked_reason_missing",
                "Blocked/not_applicable qualitative review requires a concrete blocker, skipped reason, or delegation unavailable reason.",
            )
        surface_gate = first_present(
            result,
            [
                "surface_field_review_gate",
                "quality_review.surface_field_review_gate",
                "qualitative_review.surface_field_review_gate",
                "result.surface_field_review_gate",
                "result.quality_review.surface_field_review_gate",
            ],
        )
        surface_required = any(
            boolish(first_present(result, [path]))
            for path in (
                "surface_field_review_required",
                "surface_field_review_gate.required_for_acceptance",
                "surface_field_review_gate.decision_contribution_allowed",
                "quality_review.surface_field_review_required",
                "quality_review.surface_field_review_gate.required_for_acceptance",
                "quality_review.surface_field_review_gate.decision_contribution_allowed",
                "qualitative_review.surface_field_review_required",
                "qualitative_review.surface_field_review_gate.required_for_acceptance",
                "qualitative_review.surface_field_review_gate.decision_contribution_allowed",
                "result.surface_field_review_required",
                "result.surface_field_review_gate.required_for_acceptance",
                "result.surface_field_review_gate.decision_contribution_allowed",
                "result.quality_review.surface_field_review_required",
                "result.quality_review.surface_field_review_gate.required_for_acceptance",
                "result.quality_review.surface_field_review_gate.decision_contribution_allowed",
            )
        )
        if surface_required and not isinstance(surface_gate, dict):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_surface_required_missing",
                "A required active-surface review gate must be present before an acceptance decision.",
            )
        if isinstance(surface_gate, dict):
            aggregate_status_value = surface_gate.get("surface_field_review_status")
            aggregate_status = (
                aggregate_status_value.strip().lower()
                if isinstance(aggregate_status_value, str)
                else "invalid_contract"
            )
            if aggregate_status not in {"pass", "fail", "not_applicable", "not_evaluated", "invalid_contract"}:
                aggregate_status = "invalid_contract"
            aggregate_pass = aggregate_status == "pass"
            surface_claim_relevant = aggregate_pass or surface_required
            if surface_required and aggregate_status not in {"pass", "not_applicable"}:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "qualitative_review_surface_required_not_passed",
                    "A required active-surface review must pass or be explicitly not_applicable before acceptance.",
                    {"surface_field_review_status": "invalid_contract" if aggregate_status == "invalid_contract" else aggregate_status},
                )
            classes_value = surface_gate.get("surface_field_classes")
            malformed_class_ids = False
            classes: list[str] = []
            if isinstance(classes_value, list):
                for item in classes_value:
                    normalized = _opaque_id(item)
                    if normalized is None:
                        malformed_class_ids = True
                    else:
                        classes.append(normalized)
            elif classes_value is not None:
                malformed_class_ids = True
            rows_value = surface_gate.get("field_class_results")
            if isinstance(rows_value, dict):
                rows = []
                for key, value in rows_value.items():
                    field_class_id = _opaque_id(key)
                    if field_class_id is None or not isinstance(value, dict):
                        malformed_class_ids = True
                        continue
                    rows.append(dict(value, field_class_id=field_class_id))
            else:
                rows = rows_value if isinstance(rows_value, list) else []
                if rows_value is not None and not isinstance(rows_value, list):
                    malformed_class_ids = True
            if any(not isinstance(row, dict) for row in rows):
                malformed_class_ids = True
                rows = [row for row in rows if isinstance(row, dict)]
            row_ids = [
                normalized
                for row in rows
                if (normalized := _opaque_id(row.get("field_class_id"))) is not None
            ]
            if any(_opaque_id(row.get("field_class_id")) is None for row in rows):
                malformed_class_ids = True
            rows_by_id = {
                normalized: row
                for row in rows
                if (normalized := _opaque_id(row.get("field_class_id"))) is not None
            }
            unresolved: list[dict[str, object]] = []
            if malformed_class_ids:
                unresolved.append({"field_class_id": None, "reason": "field_class_id_malformed"})
            if boolish(surface_gate.get("field_class_map_missing")):
                unresolved.append({"field_class_id": None, "reason": "field_class_map_missing"})
            inventory_not_applicable = str(
                surface_gate.get("surface_field_inventory_status")
                or surface_gate.get("surface_field_review_status")
                or ""
            ).strip().lower() == "not_applicable"
            if surface_claim_relevant and not classes and not inventory_not_applicable:
                unresolved.append({"field_class_id": None, "reason": "field_class_inventory_empty"})
            if aggregate_pass and inventory_not_applicable:
                unresolved.append({"field_class_id": None, "reason": "not_applicable_inventory_marked_pass"})
            duplicate_ids = sorted(
                {
                    field_id
                    for field_id in {*classes, *row_ids}
                    if classes.count(field_id) > 1 or row_ids.count(field_id) > 1
                }
            )
            unresolved.extend(
                {"field_class_id": field_id, "reason": "duplicate_or_conflicting_rows"}
                for field_id in duplicate_ids
            )
            allowed_applicability = {"applicable", "not_applicable", "insufficient_evidence", "invalid_contract"}
            allowed_review = {"pass", "fail", "not_observed", "not_evaluated"}
            allowed_substance = {"meaningful", "not_meaningful", "not_applicable", "insufficient_evidence", "invalid_contract"}
            matrix_value = surface_gate.get("surface_field_defect_matrix")
            if matrix_value is None:
                matrix_value = first_present(
                    result,
                    [
                        "surface_field_defect_matrix",
                        "quality_review.surface_field_defect_matrix",
                        "qualitative_review.surface_field_defect_matrix",
                    ],
                )
            matrix_by_id: dict[str, dict[str, object]] = {}
            matrix_malformed = False
            if matrix_value is not None:
                if not isinstance(matrix_value, dict):
                    matrix_malformed = True
                else:
                    for key, counts in matrix_value.items():
                        field_class_id = _opaque_id(key)
                        if field_class_id is None or not _scalar_counts_valid(counts):
                            matrix_malformed = True
                            continue
                        matrix_by_id[field_class_id] = counts
            if matrix_malformed:
                unresolved.append({"field_class_id": None, "reason": "defect_matrix_malformed"})
            for field_class_id in classes:
                row = rows_by_id.get(field_class_id)
                if not row:
                    unresolved.append({"field_class_id": field_class_id, "reason": "row_missing"})
                    continue
                applicability = str(row.get("applicability_status") or "applicable").strip().lower()
                review_value = str(row.get("review_status") or "not_evaluated").strip().lower()
                substance = str(row.get("referential_substance_status") or "").strip().lower()
                if applicability not in allowed_applicability or review_value not in allowed_review or (substance and substance not in allowed_substance):
                    unresolved.append({"field_class_id": field_class_id, "reason": "invalid_status"})
                    continue
                if applicability == "not_applicable":
                    continue
                observed_count = row.get("observed_count")
                row_defect_counts = row.get("defect_counts")
                defect_counts_valid = _scalar_counts_valid(row_defect_counts)
                matrix_counts = matrix_by_id.get(field_class_id)
                matrix_conflict = matrix_value is not None and (
                    matrix_counts is None or not defect_counts_valid or matrix_counts != row_defect_counts
                )
                locator_status = str(row.get("locator_status") or "").strip().lower()
                locator_present = locator_status == "present"
                referential_not_applicable = locator_status == "not_applicable" and substance == "not_applicable"
                referential_unresolved = not referential_not_applicable and (
                    not locator_present or substance != "meaningful"
                )
                if (
                    applicability != "applicable"
                    or review_value != "pass"
                    or not isinstance(observed_count, int)
                    or isinstance(observed_count, bool)
                    or observed_count <= 0
                    or referential_unresolved
                    or not defect_counts_valid
                    or _nonzero_scalar(row_defect_counts)
                    or matrix_conflict
                ):
                    unresolved.append(
                        {
                            "field_class_id": field_class_id,
                            "reason": (
                                "defect_projection_conflict"
                                if matrix_conflict
                                else "not_substantively_reviewed"
                                if referential_unresolved
                                else "not_fully_reviewed"
                            ),
                        }
                    )
            if unresolved:
                add(
                    findings,
                    ("block" if mode == "block" else "warn") if surface_claim_relevant else "warn",
                    "qualitative_review_surface_class_bypass",
                    "An aggregate or required surface review cannot hide an active field class that was not observed and referentially reviewed.",
                    {"unresolved_field_classes": unresolved},
                )
        density_status_value = first_present(
            result,
            [
                "substance_density_evaluation_status",
                "substance_density_gate.evaluation_status",
                "quality_review.substance_density_evaluation_status",
                "quality_review.substance_density_gate.evaluation_status",
                "qualitative_review.substance_density_evaluation_status",
                "qualitative_review.substance_density_gate.evaluation_status",
                "result.substance_density_evaluation_status",
                "result.substance_density_gate.evaluation_status",
                "result.quality_review.substance_density_evaluation_status",
                "result.quality_review.substance_density_gate.evaluation_status",
            ],
        )
        density_required = any(
            boolish(first_present(result, [path]))
            for path in (
                "substance_density_required",
                "substance_density_gate.required_for_acceptance",
                "substance_density_gate.decision_contribution_allowed",
                "quality_review.substance_density_required",
                "quality_review.substance_density_gate.required_for_acceptance",
                "quality_review.substance_density_gate.decision_contribution_allowed",
                "qualitative_review.substance_density_required",
                "qualitative_review.substance_density_gate.required_for_acceptance",
                "qualitative_review.substance_density_gate.decision_contribution_allowed",
                "result.substance_density_required",
                "result.substance_density_gate.required_for_acceptance",
                "result.substance_density_gate.decision_contribution_allowed",
                "result.quality_review.substance_density_required",
                "result.quality_review.substance_density_gate.required_for_acceptance",
                "result.quality_review.substance_density_gate.decision_contribution_allowed",
            )
        )
        if density_required and density_status_value is None:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_substance_density_required_missing",
                "A required referential-substance projection must be present before an acceptance decision.",
            )
        if density_status_value is not None:
            density_allowed = {
                "meaningful",
                "not_meaningful",
                "not_applicable",
                "insufficient_evidence",
                "invalid_contract",
            }
            density_status_candidate = (
                density_status_value.strip().lower()
                if isinstance(density_status_value, str)
                else "invalid_contract"
            )
            density_status = (
                density_status_candidate
                if density_status_candidate in density_allowed
                else "invalid_contract"
            )
            density_counts = first_present(
                result,
                [
                    "referential_substance_counts",
                    "quality_review.referential_substance_counts",
                    "qualitative_review.referential_substance_counts",
                    "result.referential_substance_counts",
                    "result.quality_review.referential_substance_counts",
                ],
            )
            density_claim_relevant = density_required or density_status in {"meaningful", "not_meaningful"}
            density_unresolved = density_status not in density_allowed or density_status in {
                "not_meaningful",
                "insufficient_evidence",
                "invalid_contract",
            }
            density_not_applicable = density_status == "not_applicable"
            density_counts_invalid = not density_not_applicable and density_counts is not None and not _scalar_counts_valid(density_counts)
            meaningful_count = (
                density_counts.get("meaningful")
                if isinstance(density_counts, dict)
                else None
            )
            meaningful_status_without_evidence = bool(
                density_status == "meaningful"
                and (
                    not _finite_nonnegative_number(meaningful_count)
                    or meaningful_count == 0
                )
            )
            density_defects = not density_not_applicable and isinstance(density_counts, dict) and _nonzero_scalar(
                {
                    key: density_counts.get(key)
                    for key in ("opaque", "incompatible_collision", "possible_false_split")
                }
            )
            if not density_not_applicable and (
                density_unresolved
                or density_counts_invalid
                or density_defects
                or meaningful_status_without_evidence
            ):
                add(
                    findings,
                    ("block" if mode == "block" else "warn") if density_claim_relevant else "warn",
                    "qualitative_review_referential_substance_bypass",
                    "A required or consumed density projection cannot support review while referential substance is unresolved or defective.",
                    {
                        "evaluation_status": density_status,
                        "scalar_counts_invalid": density_counts_invalid,
                        "scalar_defects_present": bool(density_defects),
                        "meaningful_evidence_present": not meaningful_status_without_evidence,
                    },
                )
