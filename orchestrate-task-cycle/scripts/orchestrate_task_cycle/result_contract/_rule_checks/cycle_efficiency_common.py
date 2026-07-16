from __future__ import annotations

import re


ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
STATUSES = {"ok", "warn", "blocked"}
RECOMMENDATIONS = {
    "continue",
    "batch_micro_contracts",
    "supply_evidence_path",
    "bounded_preflight",
    "supply_evidence_path_or_bounded_preflight",
    "resume_primary_output",
    "root_cause_repair_or_stop_with_blocker",
    "narrow_scope",
    "register_consolidation_candidate",
    "stop_with_blocker",
    "consume_or_reorder_task_pack_or_terminal_block",
    "route_validation_set_plan_or_build",
}
BASIS_LIST_FIELDS = {
    "unique_new_artifact_ids",
    "unique_unchanged_artifact_ids",
    "fresh_stage_event_ids",
}
OPAQUE_ID_MAX_LENGTH = 128
PROFILE_SCOPE_FIELDS = {
    "goal_axis",
    "root_family_key",
    "producer_lineage",
    "artifact_class",
    "decision_lane",
    "input_cohort",
}
EXECUTION_SCOPE_FIELDS = {
    "goal_axis",
    "producer_lineage",
    "artifact_class",
    "decision_lane",
}
EXECUTION_SCOPE_EVIDENCE_FIELDS = EXECUTION_SCOPE_FIELDS | {
    "execution_starvation_window"
}


def bounded_opaque_id(value: object, *, path_safe: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > OPAQUE_ID_MAX_LENGTH:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        return None
    if path_safe and not ID_PATTERN.fullmatch(text):
        return None
    return text


def bounded_id_list(value: object, *, allow_empty: bool = True) -> bool:
    return bool(
        isinstance(value, list)
        and (allow_empty or value)
        and all(bounded_opaque_id(item) is not None for item in value)
        and len(value) == len(set(value))
    )


def nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
