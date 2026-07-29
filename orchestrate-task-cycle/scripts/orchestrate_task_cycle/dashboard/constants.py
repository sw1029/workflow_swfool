from __future__ import annotations

import re

from ..ledger.constants import CANONICAL_STEP_ORDER
from ..result_contract.finalization import VERDICT_AXES


DEFAULT_STEPS = list(CANONICAL_STEP_ORDER)
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
