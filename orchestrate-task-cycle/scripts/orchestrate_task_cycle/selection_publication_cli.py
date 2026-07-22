"""CLI boundary for recoverable selected-task publication."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .selection_publication import (
    migrate_publication_state,
    prepare_drift_reconciliation,
    prepare_publication,
    prepare_publication_intent,
    publication_status,
    publish_prepared,
    recover_publications,
)


def _read_plan(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("selection-publication plan must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--plan", required=True)
    apply = commands.add_parser("apply")
    apply.add_argument("--plan", required=True)
    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("--plan", required=True)
    recover = commands.add_parser("recover")
    recover.add_argument("--transaction-id")
    prepare_intent = commands.add_parser("prepare-intent")
    prepare_intent.add_argument("--intent", required=True)
    apply_intent = commands.add_parser("apply-intent")
    apply_intent.add_argument("--intent", required=True)
    reconcile_current = commands.add_parser("reconcile-current")
    reconcile_current.add_argument("--source-ref", required=True)
    reconcile_current.add_argument("--source-sha256", required=True)
    commands.add_parser("migrate-state")
    status = commands.add_parser("status")
    status.add_argument("--deep", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root)
    try:
        if args.command == "prepare":
            result = prepare_publication(root, _read_plan(args.plan))
        elif args.command == "apply":
            prepared = prepare_publication(root, _read_plan(args.plan))
            result = publish_prepared(root, str(prepared["transaction_id"]))
        elif args.command == "reconcile":
            prepared = prepare_drift_reconciliation(root, _read_plan(args.plan))
            result = publish_prepared(root, str(prepared["transaction_id"]))
        elif args.command == "recover":
            result = recover_publications(root, args.transaction_id)
        elif args.command == "prepare-intent":
            result = prepare_publication_intent(root, _read_plan(args.intent))
        elif args.command == "apply-intent":
            prepared = prepare_publication_intent(root, _read_plan(args.intent))
            result = publish_prepared(root, str(prepared["transaction_id"]))
        elif args.command == "reconcile-current":
            intent = {
                "schema_version": 1,
                "kind": "selection_publication_intent",
                "source_decision": {
                    "ref": args.source_ref,
                    "sha256": args.source_sha256,
                },
                "task_source": None,
                "owner_receipts": [],
            }
            prepared = prepare_publication_intent(root, intent)
            result = publish_prepared(root, str(prepared["transaction_id"]))
        elif args.command == "migrate-state":
            result = migrate_publication_state(root)
        else:
            result = publication_status(root, deep=args.deep)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"status": "blocked", "error": str(exc), "mutation_performed": False}
            )
        )
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0
