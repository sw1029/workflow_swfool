from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .context import PacketBuildContext
from .specs_setup import (
    build_repo_skill_adapter_scan,
    build_acceptance,
    build_validation_scope_plan,
    build_governance,
    build_validation_set_plan,
    build_repo_skill_adapter_validate,
    build_code_structure_audit,
    build_run,
)
from .specs_evidence import (
    build_qualitative_review,
    build_loopback_audit,
    build_validation_set_build,
    build_visible_increment,
    build_repo_skill_gap_analysis,
    build_cycle_efficiency_profile,
    build_validation_scope_finalize,
    build_index_pre_validate,
)
from .specs_completion import (
    build_schema_pre_derive,
    build_derive,
    build_schema_post_derive,
    build_index,
    build_validate,
)
from .specs_close import (
    build_issue,
    build_commit,
    build_dashboard,
    build_report,
    build_closeout_commit,
)


TargetBuilder = Callable[[PacketBuildContext], dict[str, Any]]

TARGET_BUILDERS: dict[str, TargetBuilder] = {
    "repo_skill_adapter_scan": build_repo_skill_adapter_scan,
    "acceptance": build_acceptance,
    "validation_scope_plan": build_validation_scope_plan,
    "governance": build_governance,
    "validation_set_plan": build_validation_set_plan,
    "repo_skill_adapter_validate": build_repo_skill_adapter_validate,
    "code_structure_audit": build_code_structure_audit,
    "run": build_run,
    "qualitative_review": build_qualitative_review,
    "loopback_audit": build_loopback_audit,
    "validation_set_build": build_validation_set_build,
    "visible_increment": build_visible_increment,
    "repo_skill_gap_analysis": build_repo_skill_gap_analysis,
    "cycle_efficiency_profile": build_cycle_efficiency_profile,
    "validation_scope_finalize": build_validation_scope_finalize,
    "index_pre_validate": build_index_pre_validate,
    "schema_pre_derive": build_schema_pre_derive,
    "derive": build_derive,
    "schema_post_derive": build_schema_post_derive,
    "index": build_index,
    "validate": build_validate,
    "issue": build_issue,
    "commit": build_commit,
    "dashboard": build_dashboard,
    "report": build_report,
    "closeout_commit": build_closeout_commit,
}
