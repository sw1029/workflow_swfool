from __future__ import annotations

from pathlib import Path

from .. import model_effort_router


ORDER = [
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

TRANSITION_REQUIREMENTS = {
    f"pre_{step}": ORDER[:index] for index, step in enumerate(ORDER)
}

BOOTSTRAP_ORDER = [
    "context",
    "authority",
    "schema_pre_derive",
    "derive",
    "schema_post_derive",
    "index",
]
BOOTSTRAP_TRANSITION_REQUIREMENTS = {
    **{
        f"pre_{step}": BOOTSTRAP_ORDER[:index]
        for index, step in enumerate(BOOTSTRAP_ORDER)
    },
    "bootstrap_complete": BOOTSTRAP_ORDER,
}

TERMINAL_OK = {
    "complete",
    "completed",
    "ok",
    "passed",
    "partial",
    "not_applicable",
    "skipped",
}
SUCCESS_WORDS = {"success", "succeeded", "passed", "complete", "completed"}
STEP_ALIASES = {
    "context": ["establish_state"],
    "code_structure_audit": ["module_boundary_audit", "structure_audit"],
    "run": ["run_log"],
    "qualitative_review": ["output_quality_review"],
    "loopback_audit": ["anti_loop_audit", "loopback"],
    "issue": ["issue_tracking"],
    "closeout_commit": ["closeout"],
}

MODEL_EFFORT_PROFILE_PATH = (
    Path(__file__).resolve().parents[3] / "references" / "model-effort-profiles.json"
)
MODEL_EFFORT_ROUTER = model_effort_router
MODEL_EFFORT_POLICY = MODEL_EFFORT_ROUTER.load_policy(MODEL_EFFORT_PROFILE_PATH)
SUPPORTED_AGENT_MODELS = {str(item) for item in MODEL_EFFORT_POLICY["models"].values()}
CODE_WORKER_MODEL = str(MODEL_EFFORT_POLICY["tiers"]["2"]["model"])
SUPPORTED_AGENT_EFFORTS = {
    str(item) for item in MODEL_EFFORT_POLICY["supported_efforts"]
}
ROUTING_ENFORCEMENT_VALUES = {
    str(item) for item in MODEL_EFFORT_POLICY["result_enforcement_values"]
}
ROUTING_REQUIRED_TARGETS = {
    "governance",
    "validation_set_plan",
    "qualitative_review",
    "loopback_audit",
    "validation_set_build",
    "schema_pre_derive",
    "derive",
    "schema_post_derive",
    "index",
    "validate",
    "issue",
    "commit",
    "closeout_commit",
}
SUBSTANTIVE_BOOTSTRAP_STATUSES = {"complete", "completed", "ok", "passed"}
PLACEHOLDER_IDS = {
    "",
    "unknown",
    "none",
    "null",
    "n/a",
    "na",
    "not_applicable",
    "pending",
    "todo",
}
