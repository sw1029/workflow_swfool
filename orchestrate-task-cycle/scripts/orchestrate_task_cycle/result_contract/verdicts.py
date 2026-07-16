from __future__ import annotations

from typing import Any

from .common import add, first_present, non_empty, value_for
from .receipts import _declared_values, _normalized_verdict_status, _positive_decision_claim

VERDICT_AXES = (
    "task_acceptance_verdict",
    "artifact_truth_verdict",
    "artifact_semantic_verdict",
    "pack_transition_verdict",
    "historical_index_verdict",
    "goal_readiness_verdict",
)
VERDICT_AXIS_STATUSES = {
    "pass",
    "fail",
    "partial",
    "blocked",
    "not_evaluated",
    "not_applicable",
    "conflicted",
}

def validate_verdict_axes(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    declared = {
        axis: _declared_values(
            result,
            (
                axis,
                f"verdict_axes.{axis}",
                f"result.{axis}",
                f"result.verdict_axes.{axis}",
                f"authoritative_projection.{axis}",
                f"finalization.authoritative_projection.{axis}",
                f"result.authoritative_projection.{axis}",
            ),
        )
        for axis in VERDICT_AXES
    }
    raw_version = first_present(
        result,
        ["verdict_contract_version", "verdict_axes.schema_version", "result.verdict_contract_version"],
    )
    try:
        contract_version = int(raw_version) if raw_version is not None else None
    except (TypeError, ValueError):
        contract_version = None
    any_axes = any(values for values in declared.values())
    current_required = target in {"validate", "derive", "report"} and _positive_decision_claim(target, result)
    severity = (
        "block"
        if mode == "block"
        or target in {"validate", "report"}
        or _positive_decision_claim(target, result)
        else "warn"
    )
    if raw_version is None and (any_axes or current_required):
        add(
            findings,
            severity,
            "verdict_contract_version_missing",
            "Lifecycle verdicts require version 1; legacy packets require explicit version 0.",
        )
        return
    if raw_version is not None and contract_version not in {0, 1}:
        add(findings, severity, "verdict_contract_version_invalid", "Verdict contract version must be 1 or explicit legacy version 0.")
        return
    if contract_version == 0:
        return
    if contract_version != 1 and not any_axes:
        return
    statuses: dict[str, str] = {}
    for axis, values in declared.items():
        if not values:
            add(findings, severity, "verdict_axis_missing", "Current verdict-axis packets must preserve every lifecycle verdict axis.", {"axis": axis})
            continue
        observed_statuses = {_normalized_verdict_status(value) for value in values}
        if len(observed_statuses) > 1:
            status = "conflicted"
            add(
                findings,
                severity,
                "verdict_axis_conflicted",
                "Duplicate current surfaces disagree on one verdict axis; preserve the axis as conflicted instead of selecting a favorable value.",
                {"axis": axis, "observed_statuses": sorted(observed_statuses)},
            )
        else:
            status = next(iter(observed_statuses))
        statuses[axis] = status
        if status not in VERDICT_AXIS_STATUSES:
            add(findings, severity, "verdict_axis_status_invalid", "Verdict axis status is invalid.", {"axis": axis, "status": status})
        for value in values:
            value_status = _normalized_verdict_status(value)
            evidence = value.get("evidence_ref") or value.get("evidence_refs") if isinstance(value, dict) else None
            if value_status != "not_applicable" and not non_empty(evidence):
                add(findings, severity, "verdict_axis_evidence_missing", "Verdict axes require a bounded evidence reference.", {"axis": axis})
                break
    goal_status = statuses.get("goal_readiness_verdict")
    implementation_blocking = {
        axis
        for axis in ("task_acceptance_verdict", "artifact_truth_verdict", "artifact_semantic_verdict")
        if statuses.get(axis) in {"fail", "blocked", "partial", "not_evaluated", "conflicted"}
    }
    readiness_blocking = {
        axis
        for axis in VERDICT_AXES[:-1]
        if statuses.get(axis) in {"fail", "blocked", "partial", "not_evaluated", "conflicted"}
    }
    if implementation_blocking and str(value_for(result, "progress_verdict") or "").lower() == "advanced":
        add(
            findings,
            severity,
            "implementation_axis_failure_counted_as_progress",
            "Task acceptance, artifact truth, or artifact semantic failure cannot be upgraded to advanced progress.",
            {"blocking_axes": sorted(implementation_blocking)},
        )
    if readiness_blocking and goal_status == "pass":
        add(
            findings,
            severity,
            "failed_axis_counted_as_goal_ready",
            "Goal readiness cannot pass while a required lifecycle axis is failed, blocked, partial, not evaluated, or conflicted.",
            {"blocking_axes": sorted(readiness_blocking)},
        )
    failed_axes = {
        axis
        for axis, status in statuses.items()
        if status in {"fail", "blocked", "partial", "not_evaluated", "conflicted"}
    }
    retry_axis = str(first_present(result, ["retry_axis", "selected_remediation_axis", "derive.retry_axis"]) or "").strip()
    if target == "derive" and failed_axes and retry_axis and retry_axis not in failed_axes:
        add(
            findings,
            severity,
            "derive_retry_axis_mismatch",
            "Derive retry routing must target an actually failed verdict axis.",
            {"retry_axis": retry_axis, "failed_axes": sorted(failed_axes)},
        )

