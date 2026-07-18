"""Policy validation and disposition for selection-tick comparisons."""

from __future__ import annotations

import re
from typing import Any, Sequence

from .selection_tick_limits import MAX_POLICY_IDS


DEFAULT_WAKE_PREDICATES = ("watched-class-digest-changed",)
DEFAULT_MINIMUM_MATERIAL_DELTA = "one-watched-class-digest-change"
EVIDENCE_CLASSES = {
    "task_state",
    "goal_truth",
    "authority",
    "advice",
    "issue",
    "schema_contract",
    "adapter",
    "task_pack",
    "custom_watch",
    "exact_subject",
}


def opaque_ids(
    values: Sequence[str], label: str, *, max_count: int = MAX_POLICY_IDS
) -> list[str]:
    """Return unique bounded opaque IDs or reject the input."""

    if len(values) > max_count:
        raise ValueError(f"{label} count exceeds {max_count}")
    if any(not isinstance(item, str) for item in values):
        raise ValueError(f"{label} must contain strings")
    result = list(dict.fromkeys(item.strip() for item in values if item.strip()))
    if not result or any(
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", item) for item in result
    ):
        raise ValueError(f"{label} must contain bounded opaque IDs")
    return result


def selection_policy(
    previous: dict[str, Any] | None,
    wake_predicates: Sequence[str],
    watched_evidence_classes: Sequence[str],
    minimum_material_delta: str,
) -> tuple[str, list[str], list[str], str]:
    """Resolve immutable comparison policy from a prior baseline or new inputs."""

    if not isinstance(minimum_material_delta, str):
        raise ValueError("minimum_material_delta must be a string")
    requested_minimum = minimum_material_delta.strip()
    if previous:
        previous_sha_value = previous.get("observed_input_manifest_sha256")
        if previous_sha_value is not None and not isinstance(previous_sha_value, str):
            raise ValueError("previous observed manifest must be a string or null")
        previous_sha = (previous_sha_value or "").lower().removeprefix("sha256:")
        if previous_sha and not re.fullmatch(r"[0-9a-f]{64}", previous_sha):
            raise ValueError(
                "previous observed_input_manifest_sha256 must be a SHA-256 digest"
            )
        predicates = opaque_ids(
            previous.get("wake_predicates", []), "previous wake_predicates"
        )
        classes = opaque_ids(
            previous.get("watched_evidence_classes", []),
            "previous watched_evidence_classes",
        )
        previous_minimum = previous.get("minimum_material_delta")
        if not isinstance(previous_minimum, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", previous_minimum
        ):
            raise ValueError(
                "previous selection-tick packet has invalid minimum_material_delta"
            )
        minimum = previous_minimum
        if wake_predicates and list(dict.fromkeys(wake_predicates)) != predicates:
            raise ValueError("wake predicates cannot change while comparing a baseline")
        if (
            watched_evidence_classes
            and list(dict.fromkeys(watched_evidence_classes)) != classes
        ):
            raise ValueError(
                "watched evidence classes cannot change while comparing a baseline"
            )
        if (
            requested_minimum != DEFAULT_MINIMUM_MATERIAL_DELTA
            and requested_minimum != minimum
        ):
            raise ValueError(
                "minimum material delta cannot change while comparing a baseline"
            )
        return previous_sha, predicates, classes, minimum

    predicates = opaque_ids(
        wake_predicates or DEFAULT_WAKE_PREDICATES, "wake_predicates"
    )
    classes = opaque_ids(
        watched_evidence_classes or sorted(EVIDENCE_CLASSES),
        "watched_evidence_classes",
    )
    unknown_classes = sorted(set(classes) - EVIDENCE_CLASSES)
    if unknown_classes:
        raise ValueError(
            "watched evidence classes are unsupported: " + ", ".join(unknown_classes)
        )
    minimum = requested_minimum
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", minimum):
        raise ValueError("minimum_material_delta must be a bounded opaque ID")
    return "", predicates, classes, minimum


def selection_disposition(
    *,
    publication_blocked: bool,
    pending_publications: list[str],
    previous_sha: str,
    manifest_sha256: str,
    fresh_exact_premise_detected: bool,
    material_entries: list[dict[str, Any]],
) -> tuple[str, str, bool]:
    """Choose the bounded terminal-wait or derive-selection disposition."""

    if publication_blocked:
        status = "recovery_required" if pending_publications else "drift_blocked"
        reason = (
            "selection_publication_pending"
            if pending_publications
            else "selection_publication_head_drift"
        )
        return status, reason, False
    if previous_sha == manifest_sha256:
        return "no_op", "watched_selection_inputs_unchanged", False
    if not previous_sha and not fresh_exact_premise_detected:
        return "baseline_recorded", "no_previous_manifest_and_no_exact_premise", False
    if fresh_exact_premise_detected or material_entries:
        reason = (
            "fresh_exact_premise_supplied"
            if fresh_exact_premise_detected
            else "material_wake_predicate_satisfied"
        )
        return "selection_required", reason, True
    return "no_op", "changed_inputs_outside_watched_evidence_classes", False


__all__ = (
    "DEFAULT_MINIMUM_MATERIAL_DELTA",
    "DEFAULT_WAKE_PREDICATES",
    "EVIDENCE_CLASSES",
    "opaque_ids",
    "selection_disposition",
    "selection_policy",
)
