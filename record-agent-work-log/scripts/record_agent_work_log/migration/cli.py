"""Command-line adapter for agent-log migration services."""

from __future__ import annotations

import argparse
import json
import sys

from ..integrity import AgentLogIntegrityError
from .contracts import MigrationError
from .inventory import inspect_store
from .planning import write_plan
from .recovery import recover, validate_receipt
from .transaction import apply_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect, plan, apply, validate, or recover a sealed .agent_log legacy migration.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Read-only source/index/body inventory.")
    inspect_parser.add_argument("--root", required=True)
    inspect_parser.add_argument("--json", action="store_true", help="Emit JSON (the default output format).")

    plan_parser = subparsers.add_parser("plan", help="Write a deterministic zero-canonical-mutation plan.")
    plan_parser.add_argument("--root", required=True)
    plan_parser.add_argument("--expected-index-sha256", required=True)
    plan_parser.add_argument("--status-map", required=True)
    plan_parser.add_argument("--output", required=True)

    apply_parser = subparsers.add_parser("apply", help="Apply one expected-hash-bound locked transaction.")
    apply_parser.add_argument("--root", required=True)
    apply_parser.add_argument("--plan", required=True)
    apply_parser.add_argument("--expected-plan-sha256", required=True)
    apply_parser.add_argument("--expected-index-sha256", required=True)
    apply_parser.add_argument("--expected-inventory-sha256", required=True)
    apply_parser.add_argument("--dry-run", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="Validate receipt, sidecars, prefix, store, and appendability.")
    validate_parser.add_argument("--root", required=True)
    validate_parser.add_argument("--receipt", required=True)
    validate_parser.add_argument("--require-appendable", action="store_true")

    recover_parser = subparsers.add_parser("recover", help="Recover a prepared or switched transaction without history rollback.")
    recover_parser.add_argument("--root", required=True)
    recover_parser.add_argument("--transaction-id", required=True)
    return parser

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_store(args.root)
        elif args.command == "plan":
            result = write_plan(
                args.root,
                expected_index_sha256=args.expected_index_sha256,
                status_map_raw=args.status_map,
                output_raw=args.output,
            )
        elif args.command == "apply":
            result = apply_plan(
                args.root,
                plan_raw=args.plan,
                expected_plan_sha256=args.expected_plan_sha256,
                expected_index_sha256=args.expected_index_sha256,
                expected_inventory_sha256=args.expected_inventory_sha256,
                dry_run=args.dry_run,
            )
        elif args.command == "validate":
            result = validate_receipt(args.root, args.receipt, require_appendable=args.require_appendable)
        else:
            result = recover(args.root, args.transaction_id)
    except (AgentLogIntegrityError, MigrationError, OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
