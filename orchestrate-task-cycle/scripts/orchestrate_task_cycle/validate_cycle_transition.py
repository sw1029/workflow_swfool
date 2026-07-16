#!/usr/bin/env python3
"""Public facade for the composable cycle-transition validator."""

from __future__ import annotations

import argparse
import json
import sys

from .transition.access import (
    add,
    completed,
    deep_get,
    dict_list,
    extend_unique,
    first_value,
    flatten_values,
    list_value,
    load_json_arg,
    normalized_path_list,
    number_value,
    stage_event_candidates,
    status_for_step,
    step_event,
    text_blob,
    truthy,
)
from .transition.bootstrap import (
    bootstrap_binding_findings,
    explicit_task_absent,
    real_identifier,
)
from .transition.constants import (
    BOOTSTRAP_ORDER,
    BOOTSTRAP_TRANSITION_REQUIREMENTS,
    CODE_WORKER_MODEL,
    MODEL_EFFORT_POLICY,
    MODEL_EFFORT_PROFILE_PATH,
    MODEL_EFFORT_ROUTER,
    ORDER,
    PLACEHOLDER_IDS,
    ROUTING_ENFORCEMENT_VALUES,
    ROUTING_REQUIRED_TARGETS,
    STEP_ALIASES,
    SUBSTANTIVE_BOOTSTRAP_STATUSES,
    SUCCESS_WORDS,
    SUPPORTED_AGENT_EFFORTS,
    SUPPORTED_AGENT_MODELS,
    TERMINAL_OK,
    TRANSITION_REQUIREMENTS,
)
from .transition.evidence import (
    active_long_run_events,
    collect_sealed_families,
    collect_stage_semantic_signatures,
    context_active_advice,
    context_goal_truth,
    long_run_events,
    selected_disposition,
    signature_values,
    stage_advice_handling_rationale,
    stage_authority_policy,
    stage_goal_truth,
    stage_used_advice,
)
from .transition.pipeline import validate


__all__ = [
    "BOOTSTRAP_ORDER",
    "BOOTSTRAP_TRANSITION_REQUIREMENTS",
    "CODE_WORKER_MODEL",
    "MODEL_EFFORT_POLICY",
    "MODEL_EFFORT_PROFILE_PATH",
    "MODEL_EFFORT_ROUTER",
    "ORDER",
    "PLACEHOLDER_IDS",
    "ROUTING_ENFORCEMENT_VALUES",
    "ROUTING_REQUIRED_TARGETS",
    "STEP_ALIASES",
    "SUBSTANTIVE_BOOTSTRAP_STATUSES",
    "SUCCESS_WORDS",
    "SUPPORTED_AGENT_EFFORTS",
    "SUPPORTED_AGENT_MODELS",
    "TERMINAL_OK",
    "TRANSITION_REQUIREMENTS",
    "active_long_run_events",
    "add",
    "bootstrap_binding_findings",
    "collect_sealed_families",
    "collect_stage_semantic_signatures",
    "completed",
    "context_active_advice",
    "context_goal_truth",
    "deep_get",
    "dict_list",
    "explicit_task_absent",
    "extend_unique",
    "first_value",
    "flatten_values",
    "list_value",
    "load_json_arg",
    "long_run_events",
    "main",
    "normalized_path_list",
    "number_value",
    "real_identifier",
    "selected_disposition",
    "signature_values",
    "stage_advice_handling_rationale",
    "stage_authority_policy",
    "stage_event_candidates",
    "stage_goal_truth",
    "stage_used_advice",
    "status_for_step",
    "step_event",
    "text_blob",
    "truthy",
    "validate",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an orchestrate-task-cycle phase transition."
    )
    parser.add_argument(
        "--context",
        default="-",
        help="Cycle context JSON path, or '-' for stdin.",
    )
    parser.add_argument("--stage", help="Optional stage/status JSON path.")
    parser.add_argument(
        "--routing-json",
        help="Optional current target routing packet JSON path/string; kept separate from accumulated --stage ordering state.",
    )
    parser.add_argument(
        "--workflow-mode",
        choices=("normal", "bootstrap"),
        default="normal",
    )
    parser.add_argument(
        "--transition",
        default="pre_report",
        choices=sorted(
            set(TRANSITION_REQUIREMENTS) | set(BOOTSTRAP_TRANSITION_REQUIREMENTS)
        ),
        help="Transition to validate.",
    )
    args = parser.parse_args(argv)
    context = load_json_arg(args.context)
    stage = load_json_arg(args.stage) if args.stage else {}
    routing = load_json_arg(args.routing_json) if args.routing_json else None
    result = validate(context, stage, args.transition, routing, args.workflow_mode)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] != "block" else 2


if __name__ == "__main__":
    raise SystemExit(main())
