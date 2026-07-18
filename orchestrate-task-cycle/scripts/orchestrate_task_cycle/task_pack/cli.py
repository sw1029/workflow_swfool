"""Argument parser and command dispatch for the task-pack CLI."""
from __future__ import annotations

import argparse

from .consumption import command_mark_consumed
from .legacy_retirement import (
    command_activate_legacy_retirement,
    command_retire_legacy,
)
from .mutation_apply import command_apply_mutation
from .presentation import (
    command_capabilities,
    command_next,
    command_recover_replacement,
    command_render,
    command_status,
    command_validate,
)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect and render orchestrate-task-cycle task pack queues.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    status_p = sub.add_parser("status")
    status_p.add_argument("--format", choices=("json",), default="json")
    status_p.set_defaults(func=command_status)

    capabilities_p = sub.add_parser("capabilities", help="Print the deterministic task-pack schema and helper capability contract.")
    capabilities_p.set_defaults(func=command_capabilities)

    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to all packs.")
    validate_p.add_argument("--strict-findings", action="store_true", help="Exit nonzero when validation emits any finding, including warnings.")
    validate_p.set_defaults(func=command_validate)

    recover_p = sub.add_parser("recover-replacement", help="Forward-complete prepared task-pack replacement transactions.")
    recover_p.set_defaults(func=command_recover_replacement)


    render_p = sub.add_parser("render")
    render_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to all packs.")
    render_p.add_argument("--language", default="ko", help="Markdown render language label.")
    render_p.set_defaults(func=command_render)

    next_p = sub.add_parser("next")
    next_p.set_defaults(func=command_next)

    consumed_p = sub.add_parser("mark-consumed")
    consumed_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to active pack.")
    consumed_p.add_argument("--pack-coherence-json", help="Inline JSON or path containing versioned canonical before/after pack coherence fields.")
    consumed_p.add_argument("--verdict-axes-json", help="Inline JSON or path containing verdict_contract_version and all six lifecycle verdict axes.")
    consumed_p.add_argument("--item-id", required=True)
    consumed_p.add_argument("--task-id")
    consumed_p.add_argument("--task-path")
    consumed_p.add_argument("--validation-verdict")
    consumed_p.add_argument("--run-report-path")
    consumed_p.add_argument("--run-report-sha256")
    consumed_p.add_argument("--validation-report-path")
    consumed_p.add_argument("--validation-report-sha256")
    consumed_p.add_argument("--validation-evidence-path", action="append")
    consumed_p.add_argument("--issue-packet-path")
    consumed_p.add_argument("--issue-packet-sha256")
    consumed_p.add_argument("--completion-evidence-path", action="append")
    consumed_p.add_argument("--progress-verdict")
    consumed_p.add_argument("--progress-kind")
    consumed_p.add_argument("--semantic-signature")
    consumed_p.add_argument("--blocker-signature")
    consumed_p.add_argument("--has-supplied-input-delta", action="store_true")
    consumed_p.add_argument("--supplied-input-artifact-path", action="append")
    consumed_p.add_argument("--acceptance-target-met", action="store_true")
    consumed_p.add_argument("--acceptance-diluted", action="store_true")
    consumed_p.add_argument("--explicit-descope-decision", action="store_true")
    consumed_p.add_argument("--residual-item-id")
    consumed_p.add_argument("--acceptance-provenance-evidence-path", action="append")
    consumed_p.add_argument("--required-verifier")
    consumed_p.add_argument("--acceptance-verifier-status", choices=["pass", "fail", "not_evaluated"])
    consumed_p.add_argument("--acceptance-verifier-evidence-path", action="append")
    consumed_p.add_argument("--required-gate-hook", action="append")
    consumed_p.add_argument("--gate-hook-status", choices=["pass", "supplied", "present", "not_supplied", "absent", "fail_quiet", "not_evaluated"])
    consumed_p.add_argument("--pass-with-unobserved-axes", action="store_true")
    consumed_p.add_argument("--unobserved-goal-axis", action="append")
    consumed_p.add_argument("--independently-verified-field", action="append")
    consumed_p.add_argument("--producer-attested-field", action="append")
    consumed_p.add_argument("--independent-source-separation-status", choices=["pass", "missing", "overlap", "blocked", "self_grounded"])
    consumed_p.add_argument("--independently-verified-downgraded-field", action="append")
    consumed_p.add_argument("--verification-input-path", action="append")
    consumed_p.add_argument("--verified-artifact-path", action="append")
    consumed_p.add_argument("--generation-dependent-count-key", action="store_true")
    consumed_p.add_argument("--effective-count-key")
    consumed_p.add_argument("--envelope-thaw-item-required", action="store_true")
    consumed_p.add_argument("--envelope-thaw-item")
    consumed_p.add_argument("--thaw-condition")
    consumed_p.add_argument("--thaw-schedule")
    consumed_p.add_argument("--instrumentation-supply-required", action="store_true")
    consumed_p.add_argument("--diagnostics-unavailable-streak")
    consumed_p.add_argument("--existing-diagnostics-sufficient", action="store_true")
    consumed_p.add_argument("--cycle-fixed-cost")
    consumed_p.add_argument("--marginal-value-per-cycle-cost")
    consumed_p.add_argument("--residual-gap-cost-below-policy", action="store_true")
    consumed_p.add_argument("--marginal-repair-higher-value", action="store_true")
    consumed_p.add_argument("--reason")
    consumed_p.add_argument("--language", default="ko")
    consumed_p.add_argument("--render", action="store_true")
    consumed_p.set_defaults(func=command_mark_consumed)

    mutate_p = sub.add_parser(
        "apply-mutation",
        description=(
            "Apply create, replace, promote, normalize_initial_selection_provenance, insert, reorder, "
            "skip, supersede, or terminal_block from a JSON plan."
        ),
        epilog=(
            "Initial-selection schemas and end-to-end examples: "
            "orchestrate-task-cycle/references/initial-selection-provenance.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mutate_p.add_argument("--plan", required=True, help="Mutation plan JSON path, inline JSON, or '-' for stdin.")
    mutate_p.add_argument("--action", help="Override action from the plan.")
    mutate_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to active pack or plan.pack_path.")
    mutate_p.add_argument("--language", default="ko")
    mutate_p.add_argument("--render", action="store_true")
    mutate_p.add_argument("--dry-run", action="store_true", help="Validate and render the proposed in-memory state without writing the canonical pack.")
    mutate_p.set_defaults(func=command_apply_mutation)

    retire_p = sub.add_parser(
        "retire-legacy",
        help=(
            "Prepare and commit one immutable per-pack legacy retirement overlay; "
            "the overlay remains operationally inactive until authority settlement."
        ),
    )
    retire_p.add_argument("--plan", required=True, help="Closed retirement plan JSON path or inline JSON.")
    retire_p.add_argument("--dry-run", action="store_true")
    retire_p.set_defaults(func=command_retire_legacy)

    activate_p = sub.add_parser(
        "activate-legacy-retirement",
        help="Activate a committed retirement only after exact authority consumption.",
    )
    activate_p.add_argument("--completion-ref", required=True)
    activate_p.add_argument("--completion-sha256", required=True)
    activate_p.add_argument("--use-receipt-ref", required=True)
    activate_p.add_argument("--use-receipt-sha256", required=True)
    activate_p.set_defaults(func=command_activate_legacy_retirement)

    args = parser.parse_args(argv)
    return args.func(args)
