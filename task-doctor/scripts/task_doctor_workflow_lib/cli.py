from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .common import RESOLUTIONS, WorkflowError
from .journal import workspace_root
from .lifecycle import (
    apply,
    prepare,
    record_result,
    recover,
    resolve,
    resume,
    skip,
    status,
)
from .resolution import resolve_all


def _mutation_parser(subparsers: Any, name: str) -> argparse.ArgumentParser:
    result = subparsers.add_parser(name)
    result.add_argument("--root", default=".")
    result.add_argument("--workflow-id", required=True)
    result.add_argument("--expected-revision", required=True, type=int)
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Coordinate exact task-doctor owner plans without prompting or executing them."
    )
    subparsers = result.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--root", default=".")
    prepare_parser.add_argument("--plan", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--root", default=".")
    status_parser.add_argument("--workflow-id", required=True)

    resolve_parser = _mutation_parser(subparsers, "resolve")
    resolve_parser.add_argument("--operation-id", required=True)
    resolve_parser.add_argument(
        "--classification", required=True,
        choices=sorted(RESOLUTIONS - {"needs_user_approval", "already_covered",
                                      "effect_reconciliation"}),
    )
    resolve_parser.add_argument("--evidence-ref", required=True)
    resolve_parser.add_argument("--evidence-sha256", required=True)

    bundle_parser = _mutation_parser(subparsers, "resolve-all")
    bundle_parser.add_argument("--bundle-ref", required=True)
    bundle_parser.add_argument("--bundle-sha256", required=True)

    apply_parser = _mutation_parser(subparsers, "apply")
    apply_parser.add_argument("--operation-id")

    record_parser = _mutation_parser(subparsers, "record-result")
    record_parser.add_argument("--operation-id", required=True)
    record_parser.add_argument("--outcome", required=True)
    record_parser.add_argument("--evidence-ref", required=True)
    record_parser.add_argument("--evidence-sha256", required=True)

    _mutation_parser(subparsers, "resume")

    recover_parser = _mutation_parser(subparsers, "recover")
    recover_parser.add_argument("--operation-id", required=True)
    recover_parser.add_argument("--outcome", required=True)
    recover_parser.add_argument("--evidence-ref", required=True)
    recover_parser.add_argument("--evidence-sha256", required=True)

    skip_parser = _mutation_parser(subparsers, "skip")
    skip_parser.add_argument("--operation-id", required=True)
    skip_parser.add_argument("--evidence-ref", required=True)
    skip_parser.add_argument("--evidence-sha256", required=True)
    return result


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    if args.command == "prepare":
        return prepare(root, Path(args.plan).resolve())
    if args.command == "status":
        return status(root, args.workflow_id)
    if args.command == "resolve":
        return resolve(root, args.workflow_id, args.operation_id, args.classification,
                       args.evidence_ref, args.evidence_sha256, args.expected_revision)
    if args.command == "resolve-all":
        return resolve_all(root, args.workflow_id, args.bundle_ref,
                           args.bundle_sha256, args.expected_revision)
    if args.command == "apply":
        return apply(root, args.workflow_id, args.operation_id, args.expected_revision)
    if args.command == "record-result":
        return record_result(root, args.workflow_id, args.operation_id, args.outcome,
                             args.evidence_ref, args.evidence_sha256,
                             args.expected_revision)
    if args.command == "resume":
        return resume(root, args.workflow_id, args.expected_revision)
    if args.command == "recover":
        return recover(root, args.workflow_id, args.operation_id, args.outcome,
                       args.evidence_ref, args.evidence_sha256, args.expected_revision)
    if args.command == "skip":
        return skip(root, args.workflow_id, args.operation_id,
                    args.evidence_ref, args.evidence_sha256, args.expected_revision)
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        payload = dispatch(args)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except WorkflowError as error:
        payload = {
            "ok": False,
            "command": getattr(args, "command", None),
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "user_action_required": error.user_action_required,
                "next_action": error.next_action,
                "details": error.details,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return 2
