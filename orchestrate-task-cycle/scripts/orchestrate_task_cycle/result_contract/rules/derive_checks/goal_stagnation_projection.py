from __future__ import annotations

from .shared import (
    _bounded_id_items,
    _bounded_opaque_id,
    _nonnegative_int,
    add,
    boolish,
    first_present,
)
from .state import DeriveFacts


def _projection_summary(
    value: object,
) -> tuple[bool, str, list[object], int | None, int | None, int | None, int | None]:
    valid = isinstance(value, dict)
    status = ""
    family_ids: list[object] = []
    cycle_count = semantic_count = producer_count = no_movement_streak = None
    if isinstance(value, dict):
        status_value = _bounded_opaque_id(value.get("status"))
        status = status_value.lower() if status_value else ""
        goal_axis = _bounded_opaque_id(value.get("goal_axis"))
        raw_family_ids = value.get("family_ids")
        family_ids = raw_family_ids if isinstance(raw_family_ids, list) else []
        family_ids_valid = bool(
            isinstance(raw_family_ids, list)
            and all(_bounded_opaque_id(item) is not None for item in raw_family_ids)
            and len(raw_family_ids) == len(set(raw_family_ids))
        )
        cycle_count = value.get("cycle_count")
        semantic_count = value.get("semantic_movement_cycle_count")
        producer_count = value.get("producer_run_cycle_count")
        no_movement_streak = value.get("no_semantic_movement_streak")
        counts_valid = all(
            _nonnegative_int(item)
            for item in (
                cycle_count,
                semantic_count,
                producer_count,
                no_movement_streak,
            )
        )
        valid = bool(
            status in {"evaluated", "scope_unknown"}
            and family_ids_valid
            and value.get("family_change_resets_streak") is False
            and counts_valid
            and semantic_count <= producer_count <= cycle_count
            and no_movement_streak <= cycle_count
            and (
                status == "scope_unknown"
                and value.get("goal_axis") in (None, "")
                or status == "evaluated"
                and goal_axis is not None
            )
        )
    return (
        valid,
        status,
        family_ids,
        cycle_count,
        semantic_count,
        producer_count,
        no_movement_streak,
    )


def _duplicate_projection_malformed(values: list[object]) -> bool:
    signatures: set[tuple[object, ...]] = set()
    malformed = False
    for candidate in values:
        if not isinstance(candidate, dict):
            malformed = True
            continue
        status = _bounded_opaque_id(candidate.get("status"))
        goal_axis = _bounded_opaque_id(candidate.get("goal_axis"))
        family_items, families_valid = _bounded_id_items(candidate.get("family_ids"))
        counts = tuple(
            candidate.get(field)
            for field in (
                "cycle_count",
                "semantic_movement_cycle_count",
                "producer_run_cycle_count",
                "no_semantic_movement_streak",
            )
        )
        if (
            status is None
            or not families_valid
            or not all(_nonnegative_int(item) for item in counts)
            or candidate.get("family_change_resets_streak") is not False
        ):
            malformed = True
            continue
        signatures.add(
            (
                status.lower(),
                goal_axis,
                tuple(sorted(family_items)),
                *counts,
                False,
            )
        )
    return malformed or len(signatures) != 1


def check_goal_projection(facts: DeriveFacts, values: list[object]) -> None:
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    (
        projection_valid,
        projection_status,
        family_ids,
        cycle_count,
        semantic_count,
        producer_count,
        no_movement_streak,
    ) = _projection_summary(values[0])
    if _duplicate_projection_malformed(values):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_axis_stagnation_projection_conflict",
            "Duplicate goal-axis stagnation projections must be valid and converge before derive consumes movement claims.",
        )
        projection_valid = False
    if not projection_valid:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_axis_stagnation_projection_invalid",
            "Derive cannot consume malformed or family-resetting goal-axis stagnation evidence; raw input is not retained.",
        )
    projection_implies_unjustified_reset = bool(
        projection_valid
        and cycle_count
        and semantic_count == 0
        and no_movement_streak != cycle_count
    )
    explicit_reset = boolish(
        first_present(
            result,
            [
                "goal_axis_stagnation_reset",
                "goal_axis_streak_reset",
                "reset_goal_axis_stagnation",
                "goal_axis_stagnation_projection.reset_applied",
                "cycle_efficiency_profile.goal_axis_stagnation_projection.reset_applied",
            ],
        )
    )
    semantic_progress_claimed = boolish(
        first_present(
            result,
            [
                "semantic_progress",
                "output_delta.semantic_progress",
                "output_delta_gate.semantic_progress",
                "result.output_delta.semantic_progress",
            ],
        )
    )
    verified_current_movement = bool(
        projection_valid
        and projection_status == "evaluated"
        and semantic_count is not None
        and semantic_count > 0
        and producer_count is not None
        and producer_count >= semantic_count
        and no_movement_streak == 0
    )
    if projection_implies_unjustified_reset or (
        (explicit_reset or semantic_progress_claimed) and not verified_current_movement
    ):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_axis_stagnation_unjustified_reset",
            "Family change, an explicit reset, or semantic-progress wording cannot reset goal-axis stagnation without verified current-axis producer movement.",
            {
                "family_change_observed": len(family_ids) > 1,
                "explicit_reset_claimed": explicit_reset,
                "semantic_progress_claimed": semantic_progress_claimed,
                "verified_current_movement": verified_current_movement,
            },
        )


__all__ = ["check_goal_projection"]
