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
from .selection_publication_gc import apply_gc, plan_gc, restore_gc
from .selection_publication_gc_owner_validation import (
    validate_gc_owner_result,
)
from .selection_publication_reference_barrier import (
    adopt_reference_barrier,
)


def _read_plan(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("selection-publication plan must be an object")
    return value


def _read_binding(value: str, label: str) -> dict[str, str]:
    try:
        path = Path(value)
        raw = json.loads(
            path.read_text(encoding="utf-8") if path.is_file() else value
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be JSON or a JSON file") from exc
    if (
        not isinstance(raw, dict)
        or set(raw) != {"ref", "sha256"}
        or not isinstance(raw.get("ref"), str)
        or not isinstance(raw.get("sha256"), str)
    ):
        raise ValueError(f"{label} must contain exactly ref and sha256")
    return {"ref": raw["ref"], "sha256": raw["sha256"]}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser(
        "prepare", help="Replay/recover an existing legacy v1 plan; never create v1."
    )
    prepare.add_argument("--plan", required=True)
    apply = commands.add_parser(
        "apply", help="Apply/replay an existing legacy v1 recovery plan only."
    )
    apply.add_argument("--plan", required=True)
    reconcile = commands.add_parser(
        "reconcile", help="Reconcile an existing legacy v1 drift plan only."
    )
    reconcile.add_argument("--plan", required=True)
    recover = commands.add_parser(
        "recover", help="Resume the one exact pending publication transaction."
    )
    recover.add_argument("--transaction-id")
    prepare_intent = commands.add_parser(
        "prepare-intent",
        help="Compile a current schema-v2 intent; normally called by selected-successor.",
    )
    prepare_intent.add_argument("--intent", required=True)
    apply_intent = commands.add_parser(
        "apply-intent",
        help="Rejected owner-only effect; execute the selected-successor bundle.",
    )
    apply_intent.add_argument("--intent", required=True)
    reconcile_current = commands.add_parser(
        "reconcile-current",
        help="Rejected legacy schema-v1 path; retained as a diagnostic command.",
    )
    reconcile_current.add_argument("--source-ref", required=True)
    reconcile_current.add_argument("--source-sha256", required=True)
    commands.add_parser(
        "migrate-state", help="Validate and migrate legacy state to compact storage v4."
    )
    commands.add_parser(
        "adopt-reference-barrier",
        help=(
            "Adopt compiler-rendered cooperative writer mode after bounded "
            "workspace preflight."
        ),
    )
    commands.add_parser(
        "gc-plan",
        help="Plan conservative removal of unreferenced selection CAS artifacts.",
    )
    gc_apply = commands.add_parser(
        "gc-apply", help="Archive and remove one exact retention plan."
    )
    gc_apply.add_argument("--plan-id", required=True)
    gc_apply.add_argument("--authority-packet", required=True)
    gc_apply.add_argument("--pre-commit-verification", required=True)
    gc_restore = commands.add_parser(
        "gc-restore", help="Restore one previously applied retention archive."
    )
    gc_restore.add_argument("--plan-id", required=True)
    gc_restore.add_argument("--authority-packet", required=True)
    gc_restore.add_argument("--pre-commit-verification", required=True)
    gc_validate = commands.add_parser(
        "gc-validate-owner-result",
        help="Fixed authority owner-result validator for GC apply/restore.",
    )
    gc_validate.add_argument(
        "--operation",
        choices=(
            "apply_selection_publication_retention",
            "restore_selection_publication_retention",
        ),
        required=True,
    )
    gc_validate.add_argument("--owner-result-ref", required=True)
    gc_validate.add_argument("--owner-result-sha256", required=True)
    gc_validate.add_argument("--reservation-ref", required=True)
    gc_validate.add_argument("--reservation-sha256", required=True)
    gc_validate.add_argument("--pre-commit-ref", required=True)
    gc_validate.add_argument("--pre-commit-sha256", required=True)
    gc_validate.add_argument(
        "--phase", choices=("current", "historical"), default="current"
    )
    status = commands.add_parser(
        "status", help="Read compact pending/head state without enumerating history."
    )
    status.add_argument("--deep", action="store_true")
    return parser


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root)
    if args.command == "prepare":
        return prepare_publication(root, _read_plan(args.plan))
    if args.command == "apply":
        prepared = prepare_publication(root, _read_plan(args.plan))
        return publish_prepared(root, str(prepared["transaction_id"]))
    if args.command == "reconcile":
        prepared = prepare_drift_reconciliation(root, _read_plan(args.plan))
        return publish_prepared(root, str(prepared["transaction_id"]))
    if args.command == "recover":
        return recover_publications(root, args.transaction_id)
    if args.command == "prepare-intent":
        return prepare_publication_intent(root, _read_plan(args.intent))
    if args.command == "apply-intent":
        raise ValueError(
            "apply-intent is an owner-only selected-successor effect; "
            "execute the authority-bound selected-successor bundle"
        )
    if args.command == "reconcile-current":
        raise ValueError(
            "reconcile-current is a retired schema-v1 downgrade path; "
            "historical receipts remain readable but new effects are forbidden"
        )
    if args.command == "migrate-state":
        return migrate_publication_state(root)
    if args.command == "adopt-reference-barrier":
        return adopt_reference_barrier(root)
    if args.command == "gc-plan":
        return plan_gc(root)
    if args.command == "gc-apply":
        return apply_gc(
            root,
            args.plan_id,
            authority_packet=_read_binding(
                args.authority_packet, "authority packet binding"
            ),
            pre_commit_verification=_read_binding(
                args.pre_commit_verification,
                "pre-commit verification binding",
            ),
        )
    if args.command == "gc-restore":
        return restore_gc(
            root,
            args.plan_id,
            authority_packet=_read_binding(
                args.authority_packet, "authority packet binding"
            ),
            pre_commit_verification=_read_binding(
                args.pre_commit_verification,
                "pre-commit verification binding",
            ),
        )
    if args.command == "gc-validate-owner-result":
        return validate_gc_owner_result(
            root,
            operation=args.operation,
            owner_result={
                "ref": args.owner_result_ref,
                "sha256": args.owner_result_sha256,
            },
            reservation={
                "ref": args.reservation_ref,
                "sha256": args.reservation_sha256,
            },
            pre_commit_verification={
                "ref": args.pre_commit_ref,
                "sha256": args.pre_commit_sha256,
            },
            phase=args.phase,
        )
    return publication_status(root, deep=args.deep)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = _dispatch(args)
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
