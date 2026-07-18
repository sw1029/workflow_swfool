"""Vocabulary, verdict-axis, and positive-delta checks for one item."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .contracts import (
    ITEM_KIND_PATTERN,
    PROGRESS_KINDS,
    PROGRESS_TARGETS,
    VALIDATION_PROFILES,
    VERDICT_AXES,
    VERDICT_AXIS_STATUSES,
)
from .packet_io import non_empty, verdict_axis_status

FindingAdder = Callable[..., None]


def validate_item_verdicts(
    item: dict[str, Any],
    item_id: str,
    add: FindingAdder,
) -> dict[str, Any]:
    if item.get("validation_profile") not in VALIDATION_PROFILES:
        add("warn", "invalid_validation_profile", "Unexpected validation profile.", {"item_id": item_id, "validation_profile": item.get("validation_profile")})
    if item.get("progress_target") not in PROGRESS_TARGETS:
        add(
            "warn",
            "invalid_progress_target",
            "Unexpected progress target; keep work subtype in `item_kind` and use a canonical lifecycle outcome.",
            {"item_id": item_id, "progress_target": item.get("progress_target")},
        )
    progress_kind_expected = item.get("progress_kind_expected")
    if progress_kind_expected is not None and progress_kind_expected not in PROGRESS_KINDS:
        add(
            "warn",
            "invalid_progress_kind_expected",
            "`progress_kind_expected` should be goal_productive or governance_only; keep capability subtype in `item_kind`.",
            {"item_id": item_id, "progress_kind_expected": progress_kind_expected},
        )
    item_kind = item.get("item_kind")
    if item_kind is not None and (
        not isinstance(item_kind, str) or not ITEM_KIND_PATTERN.fullmatch(item_kind)
    ):
        add(
            "warn",
            "invalid_item_kind",
            "`item_kind` must be a non-empty bounded path-safe token when supplied.",
            {"item_id": item_id, "item_kind": item_kind},
        )
    if progress_kind_expected == "goal_productive" and item.get("progress_target") in {"safety_only", "no_progress"}:
        add(
            "warn",
            "progress_kind_target_mismatch",
            "A goal_productive pack item should not declare a safety_only/no_progress progress target.",
            {"item_id": item_id, "progress_target": item.get("progress_target")},
        )
    if item.get("positive_input_delta_required") is True and not item.get("required_new_input_kinds"):
        add("block", "positive_delta_kinds_missing", "Positive input delta gate requires `required_new_input_kinds`.", {"item_id": item_id})
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    raw_verdict_version = result.get("verdict_contract_version")
    try:
        verdict_version = int(raw_verdict_version) if raw_verdict_version is not None else None
    except (TypeError, ValueError):
        verdict_version = None
    supplied_verdict_axes = {axis: result.get(axis) for axis in VERDICT_AXES}
    if any(value is not None for value in supplied_verdict_axes.values()) and raw_verdict_version is None:
        add("block", "pack_verdict_contract_version_missing", "Verdict axes require explicit current version 1 or legacy version 0.", {"item_id": item_id})
    if raw_verdict_version is not None and verdict_version not in {0, 1}:
        add("block", "pack_verdict_contract_version_invalid", "Verdict contract version is invalid.", {"item_id": item_id})
    if verdict_version == 1 or any(value is not None for value in supplied_verdict_axes.values()):
        for axis, value in supplied_verdict_axes.items():
            if value is None:
                add("block", "pack_verdict_axis_missing", "Current item verdict packets must preserve every verdict axis.", {"item_id": item_id, "axis": axis})
                continue
            status_value = verdict_axis_status(value)
            if status_value not in VERDICT_AXIS_STATUSES:
                add("block", "pack_verdict_axis_invalid", "Pack item verdict axis status is invalid.", {"item_id": item_id, "axis": axis, "status": status_value})
            evidence = value.get("evidence_ref") or value.get("evidence_refs") if isinstance(value, dict) else None
            if status_value != "not_applicable" and not non_empty(evidence):
                add("block", "pack_verdict_axis_evidence_missing", "Pack item verdict axes require bounded evidence refs.", {"item_id": item_id, "axis": axis})
        goal_status = verdict_axis_status(supplied_verdict_axes.get("goal_readiness_verdict"))
        implementation_blocking = {
            axis
            for axis in ("task_acceptance_verdict", "artifact_truth_verdict", "artifact_semantic_verdict")
            if verdict_axis_status(supplied_verdict_axes.get(axis)) in {"fail", "blocked", "partial", "not_evaluated", "conflicted"}
        }
        readiness_blocking = {
            axis
            for axis in VERDICT_AXES[:-1]
            if verdict_axis_status(supplied_verdict_axes.get(axis)) in {"fail", "blocked", "partial", "not_evaluated", "conflicted"}
        }
        if implementation_blocking and str(result.get("progress_verdict") or "").lower() == "advanced":
            add(
                "block",
                "pack_implementation_failure_counted_as_progress",
                "Task acceptance, artifact truth, or artifact semantics failure cannot become advanced progress.",
                {"item_id": item_id, "blocking_axes": sorted(implementation_blocking)},
            )
        if readiness_blocking and goal_status == "pass":
            add(
                "block",
                "pack_failed_axis_counted_as_goal_ready",
                "Goal readiness cannot pass while a required lifecycle axis is failed, blocked, partial, not evaluated, or conflicted.",
                {"item_id": item_id, "blocking_axes": sorted(readiness_blocking)},
            )
    if item.get("positive_input_delta_required") is True and item.get("status") == "consumed":
        gate = result.get("positive_input_delta_gate") if isinstance(result.get("positive_input_delta_gate"), dict) else {}
        has_supplied = bool(
            result.get("has_supplied_input_delta")
            or gate.get("has_supplied_input_delta")
            or result.get("produced_domain_delta")
            or gate.get("produced_domain_delta")
            or result.get("supplied_input_artifact_paths")
            or gate.get("supplied_input_artifact_paths")
        )
        if not has_supplied:
            add(
                "warn",
                "consumed_item_missing_supplied_input_delta",
                "Consumed evidence-family pack items should record a supplied input artifact or produced_domain_delta=true; derive/result-contract gates enforce this for new progress claims.",
                {"item_id": item_id},
            )

    return result
