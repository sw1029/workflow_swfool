from __future__ import annotations

from dataclasses import dataclass

from .access import status_for_step, step_event
from .constants import ORDER
from .context import ValidationContext


LATE_TRANSITIONS = {
    "pre_loopback_audit",
    "pre_validation_set_build",
    "pre_visible_increment",
    "pre_repo_skill_gap_analysis",
    "pre_cycle_efficiency_profile",
    "pre_validation_scope_finalize",
    "pre_index_pre_validate",
    "pre_validate",
    "pre_issue",
    "pre_schema_pre_derive",
    "pre_derive",
    "pre_schema_post_derive",
    "pre_index",
    "pre_commit",
    "pre_report",
    "pre_closeout_commit",
}


@dataclass(frozen=True)
class ReasonRule:
    step: str
    transitions: frozenset[str]
    reason_fields: tuple[str, ...]
    statuses: frozenset[str]
    code: str
    message: str

    def validate(self, state: ValidationContext) -> None:
        if state.transition not in self.transitions:
            return
        event = step_event(state.stage, self.step)
        status = status_for_step(state.stage, self.step)
        if status not in self.statuses:
            return
        if any(event.get(field) for field in self.reason_fields):
            return
        state.add("block", self.code, self.message)


REASON_RULES = (
    ReasonRule(
        "qualitative_review",
        frozenset(LATE_TRANSITIONS),
        (
            "reason",
            "review_skipped_reason",
            "qualitative_review_pending_reason",
            "blockers",
        ),
        frozenset({"skipped", "not_applicable", "blocked", "failed"}),
        "qualitative_review_status_reason_missing",
        "Skipped/not-applicable/blocked qualitative output review requires a concrete reason.",
    ),
    ReasonRule(
        "validation_set_plan",
        frozenset(
            LATE_TRANSITIONS
            | {"pre_governance", "pre_repo_skill_adapter_validate", "pre_run"}
        ),
        (
            "reason",
            "validation_set_skipped_reason",
            "validation_set_blocked_reason",
            "blockers",
        ),
        frozenset({"skipped", "not_applicable", "blocked", "failed"}),
        "validation_set_plan_status_reason_missing",
        "Skipped/not-applicable/blocked validation_set_plan requires a concrete reason.",
    ),
    ReasonRule(
        "code_structure_audit",
        frozenset(LATE_TRANSITIONS | {"pre_run", "pre_qualitative_review"}),
        (
            "reason",
            "code_structure_audit_skipped_reason",
            "structure_audit_skipped_reason",
            "blockers",
        ),
        frozenset({"skipped", "not_applicable", "blocked", "failed"}),
        "code_structure_audit_status_reason_missing",
        "Skipped/not-applicable/blocked code_structure_audit requires a concrete reason.",
    ),
    ReasonRule(
        "loopback_audit",
        frozenset(LATE_TRANSITIONS - {"pre_loopback_audit"}),
        ("reason", "loopback_audit_skipped_reason", "blockers"),
        frozenset({"skipped", "not_applicable", "blocked", "failed"}),
        "loopback_audit_status_reason_missing",
        "Skipped/not-applicable/blocked loopback_audit requires a concrete reason.",
    ),
    ReasonRule(
        "validation_set_build",
        frozenset(
            LATE_TRANSITIONS - {"pre_loopback_audit", "pre_validation_set_build"}
        ),
        (
            "reason",
            "validation_set_skipped_reason",
            "validation_set_blocked_reason",
            "blockers",
        ),
        frozenset({"skipped", "not_applicable", "blocked", "failed"}),
        "validation_set_build_status_reason_missing",
        "Skipped/not-applicable/blocked validation_set_build requires a concrete reason.",
    ),
)


EARLY_REASON_FIELDS = {
    "repo_skill_adapter_scan": ("adapter_scan_skipped_reason",),
    "validation_scope_plan": ("validation_scope_skipped_reason",),
    "repo_skill_adapter_validate": ("adapter_validation_skipped_reason",),
    "repo_skill_gap_analysis": ("gap_analysis_skipped_reason",),
    "cycle_efficiency_profile": ("profile_skipped_reason",),
    "validation_scope_finalize": ("validation_scope_skipped_reason",),
    "index_pre_validate": ("index_skipped_reason",),
}


def validate_reasoned_statuses(state: ValidationContext) -> None:
    _validate_early_reason_fields(state)
    for rule in REASON_RULES:
        rule.validate(state)
    _validate_schema_status(state)
    _validate_derive_status(state)


def _validate_early_reason_fields(state: ValidationContext) -> None:
    if state.target_step not in ORDER:
        return
    target_index = ORDER.index(state.target_step)
    for step, extra_fields in EARLY_REASON_FIELDS.items():
        if ORDER.index(step) >= target_index:
            continue
        event = step_event(state.stage, step)
        status = status_for_step(state.stage, step)
        if status not in {"skipped", "not_applicable", "blocked", "failed"}:
            continue
        reason = event.get("reason") or event.get("blockers")
        if not reason:
            reason = next(
                (event.get(field) for field in extra_fields if event.get(field)),
                None,
            )
        if not reason:
            state.add(
                "block",
                f"{step}_status_reason_missing",
                f"Skipped/not-applicable/blocked `{step}` requires a concrete reason.",
            )


def _validate_schema_status(state: ValidationContext) -> None:
    if state.transition not in {
        "pre_derive",
        "pre_schema_post_derive",
        "pre_index",
        "pre_commit",
        "pre_report",
        "pre_closeout_commit",
    }:
        return
    event = step_event(state.stage, "schema_pre_derive")
    status = status_for_step(state.stage, "schema_pre_derive")
    if status in {"skipped", "not_applicable"} and not (
        event.get("reason") or event.get("schema_skipped_reason")
    ):
        state.add(
            "block",
            "schema_pre_derive_skipped_without_reason",
            "Skipped pre-derive schema refresh requires a reason.",
        )


def _validate_derive_status(state: ValidationContext) -> None:
    if state.transition not in {
        "pre_schema_post_derive",
        "pre_index",
        "pre_commit",
        "pre_dashboard",
        "pre_report",
        "pre_closeout_commit",
    }:
        return
    status = status_for_step(state.stage, "derive")
    event = step_event(state.stage, "derive")
    if status in {"pending", "deferred", "blocked", "failed"} and not (
        event.get("reason")
        or event.get("derive_pending_reason")
        or event.get("blockers")
    ):
        state.add(
            "block",
            "derive_pending_reason_missing",
            "Deferred/blocked derivation requires a pending or blocker reason.",
        )
    required = {
        "pre_schema_post_derive",
        "pre_index",
        "pre_commit",
        "pre_report",
        "pre_closeout_commit",
    }
    if state.transition in required and status is None:
        state.add(
            "warn",
            "derive_status_missing",
            "Derive status is missing; validation/report should explain whether next-task derivation completed, was deferred, or was skipped.",
        )
