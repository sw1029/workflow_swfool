from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .common import artifact_payload_identity, boolish, first_present, is_metadata_only
from .state import ObservationState, ScopeState


@dataclass(frozen=True)
class EventCollections:
    progress_values: list[str]
    progress_kinds: list[str]
    global_blockers: list[str]
    blockers: list[str]
    artifacts: list[str]
    unchanged_refs: list[dict[str, Any]]
    validation_profiles: list[str]
    global_signatures: list[str]
    signatures: list[str]
    validation_events: list[dict[str, Any]]
    validation_artifacts: list[str]
    validation_blockers: list[str]
    progress_events: list[dict[str, Any]]
    global_progress_events: list[dict[str, Any]]


@dataclass(frozen=True)
class ProgressMetrics:
    vacuous_untried_streak: int
    hypothesis_exhausted: bool
    forward_mutation_vacuous_count: int


def _duplicate_payload_refs(
    events: list[dict[str, Any]], unchanged_refs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    artifact_counts = Counter(
        identity
        for event in events
        for ref in (event.get("artifact_refs") or [])
        if isinstance(ref, dict)
        and (identity := artifact_payload_identity(ref)) is not None
    )
    unchanged_counts = Counter(
        identity
        for ref in unchanged_refs
        if (identity := artifact_payload_identity(ref)) is not None
    )
    return [
        {
            "path_or_store_ref": identity[0],
            "sha256": identity[1],
            "repeated_count": count,
            "unchanged_ref_count": unchanged_counts.get(identity, 0),
            "missing_count": count - 1 - unchanged_counts.get(identity, 0),
        }
        for identity, count in sorted(artifact_counts.items())
        if count > 1 and unchanged_counts.get(identity, 0) < count - 1
    ]


def _collect_event_lists(
    events: list[dict[str, Any]], scope: ScopeState
) -> EventCollections:
    blockers = [
        str(item)
        for event in scope.scoped_events
        for item in (event.get("blockers") or [])
    ]
    artifacts = [
        str(item) for event in events for item in (event.get("artifacts") or [])
    ]
    progress_events = [
        event
        for event in scope.decision_events
        if event.get("progress_verdict")
        or first_present(event, ("progress_kind", "effective_progress_kind"))
    ]
    global_progress_events = [
        event
        for event in events
        if event.get("progress_verdict")
        or first_present(event, ("progress_kind", "effective_progress_kind"))
    ]
    return EventCollections(
        progress_values=[
            str(event.get("progress_verdict")).lower()
            for event in scope.decision_events
            if event.get("progress_verdict")
        ],
        progress_kinds=[
            str(
                first_present(event, ("effective_progress_kind", "progress_kind"))
            ).lower()
            for event in scope.decision_events
            if first_present(event, ("effective_progress_kind", "progress_kind"))
        ],
        global_blockers=[
            str(item) for event in events for item in (event.get("blockers") or [])
        ],
        blockers=blockers,
        artifacts=artifacts,
        unchanged_refs=[
            ref
            for event in events
            for ref in (event.get("unchanged_refs") or [])
            if isinstance(ref, dict)
        ],
        validation_profiles=[
            str(event.get("validation_profile")).lower()
            for event in events
            if event.get("validation_profile")
        ],
        global_signatures=[
            str(event.get("blocker_signature")).lower()
            for event in events
            if event.get("blocker_signature")
        ],
        signatures=[
            str(event.get("blocker_signature")).lower()
            for event in scope.scoped_events
            if event.get("blocker_signature")
        ],
        validation_events=[
            event
            for event in scope.decision_events
            if str(event.get("step") or "") == "validation_set_build"
        ],
        validation_artifacts=[
            artifact
            for artifact in artifacts
            if ".validation/sets/" in artifact or ".task/validation_set/" in artifact
        ],
        validation_blockers=[
            blocker
            for blocker in blockers
            if any(
                token in blocker.lower()
                for token in (
                    "validation_set",
                    "validation set",
                    "oracle",
                    "leakage",
                    "source_class",
                    "quality",
                )
            )
        ],
        progress_events=progress_events,
        global_progress_events=global_progress_events,
    )


def _progress_metrics(scope: ScopeState) -> ProgressMetrics:
    vacuous = max(
        [
            int(value)
            for event in scope.scoped_events
            if (
                value := first_present(
                    event,
                    (
                        "vacuous_untried_streak",
                        "anti_loop_progress_gate.vacuous_untried_streak",
                    ),
                )
            )
            is not None
            and str(value).isdigit()
        ]
        or [0]
    )
    exhausted = (
        any(
            boolish(
                first_present(
                    event,
                    (
                        "hypothesis_exhausted",
                        "anti_loop_progress_gate.hypothesis_exhausted",
                    ),
                )
            )
            for event in scope.scoped_events
        )
        if not scope.profile_scope_unverified
        else False
    )
    forward_vacuous = sum(
        1
        for event in scope.scoped_events
        if boolish(
            first_present(
                event,
                (
                    "forward_mutation_vacuous",
                    "anti_loop_progress_gate.forward_mutation_vacuous",
                ),
            )
        )
    )
    return ProgressMetrics(vacuous, exhausted, forward_vacuous)


def observation_state(
    events: list[dict[str, Any]], scope: ScopeState
) -> ObservationState:
    values = _collect_event_lists(events, scope)
    progress = _progress_metrics(scope)
    return ObservationState(
        progress_values=values.progress_values,
        progress_kinds=values.progress_kinds,
        global_blockers=values.global_blockers,
        blockers=values.blockers,
        unchanged_refs=values.unchanged_refs,
        missing_unchanged_payload_refs=_duplicate_payload_refs(
            events, values.unchanged_refs
        ),
        validation_profiles=values.validation_profiles,
        global_blocker_signatures=values.global_signatures,
        blocker_signatures=values.signatures,
        validation_set_events=values.validation_events,
        validation_set_artifacts=values.validation_artifacts,
        validation_set_blockers=values.validation_blockers,
        repeated_blockers=[
            {"blocker": key, "count": count}
            for key, count in Counter(values.blockers).most_common()
            if count >= 2
        ],
        repeated_signatures=[
            {"blocker_signature": key, "count": count}
            for key, count in Counter(values.signatures).most_common()
            if count >= 2
        ],
        duplicate_artifacts=[
            {"artifact": key, "count": count}
            for key, count in Counter(values.artifacts).most_common()
            if count >= 2
        ],
        metadata_only_events=[
            event for event in values.progress_events if is_metadata_only(event)
        ],
        global_metadata_only_events=[
            event for event in values.global_progress_events if is_metadata_only(event)
        ],
        vacuous_untried_streak=progress.vacuous_untried_streak,
        hypothesis_exhausted=progress.hypothesis_exhausted,
        forward_mutation_vacuous_count=progress.forward_mutation_vacuous_count,
        full_chain_without_reason=[
            event
            for event in events
            if str(event.get("validation_profile")).lower() == "full_chain"
            and not event.get("escalation_reason")
        ],
    )
