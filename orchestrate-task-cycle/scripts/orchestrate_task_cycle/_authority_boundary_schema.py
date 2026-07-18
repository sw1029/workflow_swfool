"""Closed vocabulary and field sets for authority boundary packets."""

from __future__ import annotations

import re


DECISIONS = {
    "allowed",
    "approval_required",
    "denied",
    "waiting_external_input",
    "capability_unavailable",
    "blocked_by_goal_truth",
    "classification_repair",
    "conflict",
    "not_applicable",
}
AUTHORITY_STATUSES = {
    "granted",
    "approval_required",
    "denied",
    "unverified",
    "not_applicable",
}
LOCAL_STATUSES = {"available", "unavailable", "unverified", "not_applicable"}
EXTERNAL_STATUSES = {
    "not_required",
    "available",
    "waiting_state",
    "missing_supplyable",
    "missing_unsupplyable",
    "unavailable",
    "unverified",
    "not_applicable",
}
RISK_STATUSES = {
    "not_required",
    "accepted",
    "confirmation_required",
    "declined",
    "unverified",
    "not_applicable",
}
GOAL_STATUSES = {"aligned", "blocked", "unverified", "not_applicable"}
MUTATION_CLASSES = {
    "observe",
    "local_mutation",
    "external_mutation",
    "destructive",
}
SCOPE_KINDS = {
    "goal",
    "design",
    "task",
    "improvement",
    "action",
    "authority_policy",
}
INTENT_TYPES = {
    "grant_authority",
    "ratify_goal_truth",
    "accept_risk_or_cost",
    "supply_external_input",
    "select_design_option",
}
RANKS = {"S0", "S1", "S2", "S3", "S4"}
RISKS = {"R0", "R1", "R2", "R3"}
DECISION_CLASSES = {"D0", "D1", "D2", "D3"}

TOP_KEYS = {
    "step",
    "schema_version",
    "artifact_kind",
    "packet_id",
    "decision_binding",
    "operation_binding",
    "subject",
    "scope",
    "axes",
    "selected_grants",
    "lineage_grants",
    "approval_projection",
    "composition_receipt",
    "reservation_binding",
    "dispatch_preflight",
    "effective_authority_fingerprint",
    "evidence_ids",
    "packet_sha256",
}
DECISION_KEYS = {
    "decision_id",
    "artifact_ref",
    "artifact_sha256",
    "request_id",
    "request_sha256",
    "decision",
    "effective_authority_fingerprint",
}
OPERATION_KEYS = {
    "skill_id",
    "skill_version",
    "operation_id",
    "operation_version",
    "manifest_ref",
    "manifest_sha256",
    "manifest_status",
    "mutation_class",
}
SUBJECT_KEYS = {"kind", "ref", "digest", "revision"}
SCOPE_KEYS = {
    "cycle_id",
    "task_id",
    "pack_id",
    "attempt_id",
    "scope_kind",
    "decision_class",
    "intent_type",
    "required_source_rank",
    "risk_tier",
}
AXIS_KEYS = {
    "authority",
    "local_resolution",
    "external_input",
    "risk_cost",
    "goal_truth",
}
AXIS_ROW_KEYS = {"status", "evidence_ids"}
BINDING_KEYS = {"ref", "sha256"}
GRANT_KEYS = {"grant_id", "grant_sha256", "state_version", "policy_snapshot"}
GRANT_USE_KEYS = {
    "grant_id",
    "grant_sha256",
    "units",
    "state_version_before",
    "state_version_after",
}
RESERVATION_KEYS = {
    "applicability",
    "reservation_id",
    "artifact_ref",
    "artifact_sha256",
    "state_ref",
    "state_sha256",
    "state_version",
    "status",
    "effective_authority_fingerprint",
    "grant_uses",
}
PREFLIGHT_KEYS = {
    "status",
    "artifact_ref",
    "artifact_sha256",
    "verification_id",
    "stage",
    "reservation",
    "reservation_state",
    "grant_states",
    "request_id",
    "effective_authority_fingerprint",
    "verified_at",
}
RESERVATION_STATE_KEYS = {"ref", "sha256", "version", "status"}
GRANT_STATE_KEYS = {
    "grant_id",
    "grant_sha256",
    "state_version",
    "status",
    "remaining_uses",
    "reserved_uses",
}
APPROVAL_KEYS = set(
    "projection_id schema_version artifact_kind typed_intent request_id operation "
    "subject capabilities effect scope excluded_effects safe_alternative "
    "reason_codes exact_replay_key".split()
)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
