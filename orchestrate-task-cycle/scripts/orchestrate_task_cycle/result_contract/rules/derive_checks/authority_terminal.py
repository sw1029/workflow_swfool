from __future__ import annotations

from ....authority_boundary import AuthorityProjection, project_authority_packet
from ....authority_artifacts import (
    validate_authority_artifacts,
    workspace_root_from_metadata,
)
from .shared import _declared_values, add, boolish, selected_task_kind_value
from .state import DeriveFacts


MONITOR_KINDS = {
    "monitor_running_execution",
    "harvest_running_execution",
    "long_run_monitor",
    "long_run_harvest",
}
CLASSIFICATION_KINDS = {
    "authority_classification_repair",
    "terminal_scope_classification",
    "external_dependency_probe",
}
AUTHORITY_PACKET_PATHS = (
    "authority_packet",
    "authority_phase_packet",
    "terminal_self_resolution_gate.authority_packet",
    "anti_loop_progress_gate.terminal_self_resolution_gate.authority_packet",
    "result.terminal_self_resolution_gate.authority_packet",
)
LEGACY_PATHS = (
    "authority_classification",
    "terminal_self_resolution_gate.authority_classification",
    "anti_loop_progress_gate.terminal_self_resolution_gate.authority_classification",
    "result.terminal_self_resolution_gate.authority_classification",
)


def _finding(
    facts: DeriveFacts, code: str, message: str, evidence: object = None
) -> None:
    add(
        facts.findings,
        "block" if facts.mode == "block" else "warn",
        code,
        message,
        evidence,
    )


def _packet_candidates(value: object) -> tuple[list[object], bool]:
    if isinstance(value, list):
        return value, False
    if isinstance(value, dict):
        return [value], False
    return [], value not in (None, [], {})


def _projections(facts: DeriveFacts) -> tuple[list[AuthorityProjection], bool, bool]:
    projections: list[AuthorityProjection] = []
    malformed = False
    for value in _declared_values(facts.result, AUTHORITY_PACKET_PATHS):
        candidates, invalid_container = _packet_candidates(value)
        malformed = malformed or invalid_container
        for candidate in candidates:
            projection = project_authority_packet(candidate)
            projections.append(projection)
            malformed = malformed or not projection.valid
            if projection.status != "legacy_unverified":
                artifact_findings = validate_authority_artifacts(
                    candidate if isinstance(candidate, dict) else {},
                    workspace_root_from_metadata(facts.context.metadata),
                )
                malformed = malformed or bool(artifact_findings)
                for finding in artifact_findings:
                    add(
                        facts.findings,
                        "block",
                        str(finding["code"]),
                        str(finding["message"]),
                        finding.get("evidence"),
                    )
    legacy = bool(_declared_values(facts.result, LEGACY_PATHS))
    return projections, malformed, legacy


def _flags(facts: DeriveFacts) -> tuple[bool, bool]:
    prohibited = any(
        boolish(value)
        for value in _declared_values(
            facts.result,
            (
                "goal_terminal_prohibited",
                "terminal_self_resolution_gate.goal_terminal_prohibited",
                "anti_loop_progress_gate.goal_terminal_prohibited",
                "anti_loop_progress_gate.terminal_self_resolution_gate.goal_terminal_prohibited",
            ),
        )
    )
    unverified = any(
        boolish(value)
        for value in _declared_values(
            facts.result,
            (
                "offline_scope_unverified",
                "terminal_self_resolution_gate.offline_scope_unverified",
                "anti_loop_progress_gate.offline_scope_unverified",
                "anti_loop_progress_gate.terminal_self_resolution_gate.offline_scope_unverified",
            ),
        )
    )
    return prohibited, unverified


def _axis(projection: AuthorityProjection, name: str) -> str:
    return str(projection.axes.get(name) or "unverified")


def _terminal_wait_scope_bound(
    facts: DeriveFacts, projections: list[AuthorityProjection]
) -> bool:
    wait = facts.result.get("terminal_wait")
    baseline = wait.get("selection_tick_baseline") if isinstance(wait, dict) else None
    rows = baseline.get("watch_entries") if isinstance(baseline, dict) else None
    if not isinstance(rows, list):
        return False
    if baseline.get("format_version") != 2:
        return False
    authority_rows = {
        str(row.get("authority_scope_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("kind") == "effective_authority"
    }
    expected = {str(item.scope_id): item for item in projections if item.scope_id}
    if not expected or set(authority_rows) != set(expected):
        return False
    return all(
        row.get("effective_authority_fingerprint")
        == expected[scope_id].effective_authority_fingerprint
        and row.get("decision") == expected[scope_id].decision
        and row.get("axis_statuses") == expected[scope_id].axes
        for scope_id, row in authority_rows.items()
    )


def _check_terminal_outcome(
    facts: DeriveFacts,
    outcome: str,
    projections: list[AuthorityProjection],
    malformed: bool,
    legacy: bool,
    prohibited: bool,
    unverified: bool,
) -> None:
    if malformed or legacy or unverified or not projections:
        _finding(
            facts,
            "derive_terminal_authority_axes_unverified",
            "Terminal, wait, or escalation requires a valid scoped authority packet; legacy classifications are diagnostic only.",
        )
        return
    decisions = {projection.decision for projection in projections}
    local_available = any(
        _axis(projection, "local_resolution") == "available"
        for projection in projections
    )
    waiting = any(
        projection.decision == "waiting_external_input"
        and _axis(projection, "external_input")
        in {"waiting_state", "missing_supplyable"}
        for projection in projections
    )
    approval = "approval_required" in decisions
    local_grant_escalation = local_available and any(
        projection.decision == "approval_required"
        and projection.intent_type == "grant_authority"
        and _axis(projection, "authority") == "approval_required"
        and _axis(projection, "risk_cost") != "confirmation_required"
        for projection in projections
    )
    terminal_supported = bool(
        decisions & {"denied", "capability_unavailable", "blocked_by_goal_truth"}
    ) or any(
        projection.decision == "waiting_external_input"
        and _axis(projection, "external_input")
        in {"missing_unsupplyable", "unavailable"}
        for projection in projections
    )
    wait_supported = waiting or approval
    if outcome == "terminal_wait" and (
        not wait_supported
        or (waiting and local_available)
        or local_grant_escalation
        or decisions - {"waiting_external_input", "approval_required", "not_applicable"}
        or not _terminal_wait_scope_bound(facts, projections)
    ):
        _finding(
            facts,
            "derive_terminal_wait_authority_route_invalid",
            "terminal_wait requires an exact scoped approval/external-wait packet and matching selection-tick watch row.",
        )
    if outcome == "terminal_blocked" and (
        prohibited or local_available or approval or waiting or not terminal_supported
    ):
        _finding(
            facts,
            "derive_goal_terminal_prohibited_by_authority_axes",
            "Terminal blocking requires a verified denied, unavailable-capability, or goal-truth-blocked decision and no local resolution.",
        )
    if outcome == "user_escalation" and (
        not approval
        or local_grant_escalation
        or decisions - {"approval_required", "not_applicable"}
    ):
        _finding(
            facts,
            "derive_user_escalation_not_supported_by_authority_axes",
            "User escalation requires a scoped approval_required decision; external input and local engineering are separate axes.",
        )


def _check_selected(
    facts: DeriveFacts,
    projections: list[AuthorityProjection],
    malformed: bool,
    legacy: bool,
) -> None:
    selected_kind = selected_task_kind_value(facts.result)
    if legacy or malformed:
        if selected_kind not in CLASSIFICATION_KINDS:
            _finding(
                facts,
                "derive_authority_axes_unverified_unrecovered",
                "Legacy or invalid authority material permits only bounded classification repair.",
            )
        return
    decisions = {projection.decision for projection in projections}
    if decisions & {"classification_repair", "conflict"}:
        if selected_kind not in CLASSIFICATION_KINDS:
            _finding(
                facts,
                "derive_authority_axes_unverified_unrecovered",
                "Unverified or conflicting authority permits only bounded classification repair.",
            )
        return
    unsupplyable = any(
        projection.decision == "waiting_external_input"
        and _axis(projection, "external_input")
        in {"missing_unsupplyable", "unavailable"}
        for projection in projections
    )
    if (
        "waiting_external_input" in decisions
        and not unsupplyable
        and selected_kind not in MONITOR_KINDS
    ):
        _finding(
            facts,
            "derive_waiting_state_monitor_not_selected",
            "A scoped waiting external state must route to the existing monitor/harvest owner.",
        )
    if decisions & {"approval_required", "denied", "blocked_by_goal_truth"}:
        _finding(
            facts,
            "derive_required_user_confirmation_bypassed",
            "A normal successor cannot bypass approval, denial, or goal-truth conflict.",
        )


def check_authority_terminal(facts: DeriveFacts) -> None:
    projections, malformed, legacy = _projections(facts)
    prohibited, unverified = _flags(facts)
    if (
        not projections
        and not malformed
        and not legacy
        and not prohibited
        and not unverified
    ):
        return
    outcome = str(facts.result.get("selection_outcome") or "").lower()
    if outcome in {"terminal_wait", "terminal_blocked", "user_escalation"}:
        _check_terminal_outcome(
            facts,
            outcome,
            projections,
            malformed,
            legacy,
            prohibited,
            unverified,
        )
        return
    _check_selected(facts, projections, malformed or unverified, legacy)


__all__ = ("check_authority_terminal",)
