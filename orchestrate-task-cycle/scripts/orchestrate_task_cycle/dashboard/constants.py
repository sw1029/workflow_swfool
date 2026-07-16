from __future__ import annotations

import re

from ..result_contract.finalization import VERDICT_AXES


DEFAULT_STEPS = [
    "context",
    "authority",
    "repo_skill_adapter_scan",
    "acceptance",
    "route_plan",
    "validation_scope_plan",
    "validation_set_plan",
    "governance",
    "result_contract",
    "repo_skill_adapter_validate",
    "ledger_append",
    "code_structure_audit",
    "run",
    "qualitative_review",
    "loopback_audit",
    "validation_set_build",
    "visible_increment",
    "repo_skill_gap_analysis",
    "cycle_efficiency_profile",
    "validation_scope_finalize",
    "index_pre_validate",
    "validate",
    "issue",
    "schema_pre_derive",
    "derive",
    "schema_post_derive",
    "index",
    "commit",
    "dashboard",
    "report",
    "closeout_commit",
]
CANONICAL_STEPS = set(DEFAULT_STEPS)
CYCLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

PART_L_M_FIELDS = (
    "pass_on_stale_lane",
    "decision_metadata_revision",
    "stale_measurement_artifact",
    "axis_starved_by_missing_producer",
    "producer_supply_required",
    "portfolio_quota_exceeded",
    "unreachable_within_cycle",
    "basis_overclaim",
    "surface_field_defect_matrix",
    "lane_incompatible",
    "scale_incompatible",
    "contract_conflict",
    "destructive_disposition_blocked",
    "reharvest_before_rerun_required",
    "mutually_unsatisfiable_contract",
    "sample_as_universe_misuse",
)
AXIS_FIELDS = (
    "progress_axes",
    "goal_axis_map",
    "axis_delta",
    "axis_stall_streak",
    "goal_axis_stall",
)
VERDICT_AXIS_FIELDS = VERDICT_AXES
