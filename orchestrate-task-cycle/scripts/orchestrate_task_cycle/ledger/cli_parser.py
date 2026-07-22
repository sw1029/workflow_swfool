"""Argument parser for the cycle-ledger compatibility facade."""

from __future__ import annotations

import argparse

from .constants import (
    STAGE_COMPILER_PROTOCOL_VERSION,
    STAGE_PREPARATION_SCHEMA_VERSION,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain .task/cycle/<cycle-id> stage ledger artifacts.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Initialize a cycle ledger.")
    init_p.add_argument("--cycle-id")
    init_p.add_argument("--task-id")
    init_p.add_argument("--allow-missing-task-for-bootstrap", action="store_true")
    init_p.add_argument(
        "--stage-compiler-protocol-version",
        type=int,
        choices=(1, STAGE_COMPILER_PROTOCOL_VERSION),
        help=(
            "Compiler protocol for a new cycle (default: 2); omitted on an "
            "existing cycle preserves its initialized protocol."
        ),
    )
    init_p.add_argument(
        "--stage-preparation-schema-version",
        type=int,
        choices=(1, 2, STAGE_PREPARATION_SCHEMA_VERSION),
        help="Preparation schema for a new cycle (default: 3 with protocol v2).",
    )
    init_p.add_argument("--reason", default="cycle ledger initialized")
    init_p.add_argument("--terminal-state-json", help="Optional terminal state used to suppress an unchanged full-cycle restart.")

    append_p = sub.add_parser("append", help="Append a stage event.")
    append_p.add_argument("--cycle-id", required=True)
    append_p.add_argument("--event-json", help="JSON object, JSON file path, or '-' for stdin.")
    append_p.add_argument("--step")
    append_p.add_argument("--status")
    append_p.add_argument("--reason")
    append_p.add_argument("--task-id")
    append_p.add_argument("--completed-task-id")
    append_p.add_argument("--next-task-id")
    append_p.add_argument("--changed-file", action="append", default=[])
    append_p.add_argument("--artifact", action="append", default=[])
    append_p.add_argument("--blocker", action="append", default=[])
    append_p.add_argument("--validation-verdict")
    append_p.add_argument("--progress-verdict")
    append_p.add_argument("--task-pack-id")
    append_p.add_argument("--task-pack-item-id")
    append_p.add_argument("--task-pack-path")
    append_p.add_argument("--task-pack-status")
    append_p.add_argument("--selected-task-source")
    append_p.add_argument("--promoted-item-id")
    append_p.add_argument("--completed-item-id")
    append_p.add_argument("--blocker-signature")
    append_p.add_argument("--input-delta-gate")
    append_p.add_argument("--terminal-blocker")
    append_p.add_argument("--authority-policy")
    append_p.add_argument("--authority-policy-source")
    append_p.add_argument(
        "--allow-noncanonical-step",
        action="store_true",
        help="Allow a noncanonical step and mark it as malformed/noncanonical evidence.",
    )

    render_p = sub.add_parser("render", help="Render a ledger summary.")
    render_p.add_argument("--cycle-id", required=True)
    render_p.add_argument("--format", choices=("json", "markdown"), default="markdown")
    render_p.add_argument("--write-dashboard", action="store_true")

    current_p = sub.add_parser("current", help="Refresh and print current_stage.json.")
    current_p.add_argument("--cycle-id", required=True)

    finalize_p = sub.add_parser("finalize", help="Atomically publish one validated final candidate.")
    finalize_p.add_argument("--cycle-id", required=True)
    finalize_p.add_argument("--candidate-json", required=True, help="JSON object, JSON file path, or '-' for stdin.")

    verify_p = sub.add_parser(
        "verify-finalization",
        help="Verify a finalization receipt against its immutable snapshot and current pointer.",
    )
    verify_p.add_argument("--cycle-id", required=True)
    verify_p.add_argument(
        "--receipt-json",
        required=True,
        help="Receipt or current-pointer JSON object, file path, or '-' for stdin.",
    )
    pending_p = sub.add_parser(
        "pending-finalizations",
        help="List unresolved immutable finalization conflict records.",
    )
    pending_p.add_argument("--cycle-id", required=True)

    resolve_p = sub.add_parser(
        "resolve-pending-finalization",
        help="Resolve one pending conflict as merged or evidence-bound retired.",
    )
    resolve_p.add_argument("--cycle-id", required=True)
    resolve_p.add_argument("--pending-conflict-id", required=True)
    resolve_p.add_argument("--disposition", choices=("merged", "retired"), required=True)
    resolve_p.add_argument("--resolution-evidence-id", required=True)
    resolve_p.add_argument("--resolution-evidence-digest", required=True)
    resolve_p.add_argument("--resolution-evidence-ref", required=True)
    resolve_p.add_argument("--resolution-rationale-id", required=True)
    resolve_p.add_argument("--committed-finalization-token")
    return parser
