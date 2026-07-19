from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Any

from .common import RESOLUTIONS, WorkflowError
from .common import read_json
from .intent_compiler import (
    accept_review,
    compile_intent,
    publish_review,
    publish_workflow_plan,
)
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
from .task_transition_plan import build_task_transition_plan
from .task_transition_store import publish_task_transition_plan
from .workflow_advance import (
    advance_workflow,
    build_resolution_bundle,
    publish_resolution_bundle,
)


def _intent_projection(value: dict[str, Any], detail: str) -> dict[str, Any]:
    if detail == "full":
        return value
    review = value.get("review")
    result = {key: value[key] for key in ("ok", "status") if key in value}
    if isinstance(review, dict):
        scope = review["approval_scope"]
        result.update(
            review_id=review["review_id"],
            review_fingerprint=review["review_fingerprint"],
            uncovered_operations=copy.deepcopy(
                value.get("uncovered_operations", [])
            ),
            effects=[
                {
                    "operation_id": item["operation_id"],
                    "owner_skill": item["owner_skill"],
                    "effect_class": item["effect_class"],
                    "plan_binding": item["plan_binding"],
                    "request_sha256": item["request_sha256"],
                }
                for item in scope["operations"]
            ],
        )
    return result


def _input_object(value: str, code: str) -> dict[str, Any]:
    try:
        if value == "-":
            loaded = json.load(sys.stdin)
        elif value.lstrip().startswith("{"):
            loaded = json.loads(value)
        else:
            candidate = Path(value)
            loaded = read_json(candidate.resolve(), code)
    except (OSError, json.JSONDecodeError) as error:
        raise WorkflowError(code, f"JSON input is invalid: {error}") from error
    if not isinstance(loaded, dict):
        raise WorkflowError(code, "JSON input must be an object")
    return loaded


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
    for name in ("compile-intent", "prepare-intent"):
        intent_parser = subparsers.add_parser(name)
        intent_parser.add_argument("--root", default=".")
        intent_parser.add_argument("--intent", required=True)
        intent_parser.add_argument("--at", required=True)
        intent_parser.add_argument(
            "--detail", choices=("compact", "full"), default="compact"
        )
    accept_parser = subparsers.add_parser("accept-review")
    accept_parser.add_argument("--root", default=".")
    accept_parser.add_argument("--review-ref", required=True)
    accept_parser.add_argument("--review-sha256", required=True)
    accept_parser.add_argument("--decision", required=True)
    accept_parser.add_argument(
        "--detail", choices=("compact", "full"), default="compact"
    )
    bundle_builder = subparsers.add_parser("build-resolution-bundle")
    bundle_builder.add_argument("--root", default=".")
    bundle_builder.add_argument("--workflow-id", required=True)
    bundle_builder.add_argument("--evidence-map")
    bundle_builder.add_argument("--publish", action="store_true")
    for name in ("advance", "replay-or-route"):
        advance_parser = subparsers.add_parser(name)
        advance_parser.add_argument("--root", default=".")
        advance_parser.add_argument("--workflow-id", required=True)
        advance_parser.add_argument("--evidence-map")
        advance_parser.add_argument("--max-steps", type=int, default=8)
        if name == "advance":
            advance_parser.add_argument("--apply", action="store_true")
            advance_parser.add_argument("--at")
    task_transition = subparsers.add_parser("prepare-task-transition")
    task_transition.add_argument("--root", default=".")
    task_transition.add_argument("--transition-id", required=True)
    task_transition.add_argument(
        "--transition-kind",
        choices=("initial_task", "replace_task", "retarget_task"),
        required=True,
    )
    task_transition.add_argument("--prospective-ref", required=True)
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
    if args.command in {"compile-intent", "prepare-intent"}:
        compiled = compile_intent(
            root, _input_object(args.intent, "invalid_intent"),
            prepared_at=args.at,
        )
        if args.command == "compile-intent":
            return _intent_projection(compiled, args.detail)
        if compiled["status"] == "awaiting_exact_approval":
            published = publish_review(root, compiled["review"])
            return {
                **_intent_projection(compiled, args.detail),
                **published,
            }
        published = publish_workflow_plan(root, compiled["plan"])
        prepared = prepare(root, root / published["plan_ref"])
        return {
            **_intent_projection(compiled, args.detail),
            **published,
            "workflow": prepared,
        }
    if args.command == "accept-review":
        accepted = accept_review(
            root,
            args.review_ref,
            args.review_sha256,
            _input_object(args.decision, "invalid_review_decision"),
        )
        prepared = prepare(root, root / accepted["plan_ref"])
        if args.detail == "full":
            return {**accepted, "workflow": prepared}
        return {
            "ok": accepted["ok"],
            "status": accepted["status"],
            "plan_ref": accepted["plan_ref"],
            "plan_file_sha256": accepted["plan_file_sha256"],
            "created": accepted["created"],
            "replayed": accepted["replayed"],
            "workflow": prepared,
        }
    if args.command == "build-resolution-bundle":
        evidence = (
            None if args.evidence_map is None
            else _input_object(args.evidence_map, "invalid_resolution_seed")
        )
        bundle = build_resolution_bundle(
            root, args.workflow_id, evidence_map=evidence
        )
        return {
            "ok": True,
            "command": "build-resolution-bundle",
            "bundle": bundle,
            **(publish_resolution_bundle(root, bundle) if args.publish else {}),
        }
    if args.command in {"advance", "replay-or-route"}:
        evidence = (
            None if args.evidence_map is None
            else _input_object(args.evidence_map, "invalid_resolution_seed")
        )
        return advance_workflow(
            root, args.workflow_id, max_steps=args.max_steps,
            apply_changes=(args.command == "advance" and args.apply),
            evidence_map=evidence,
            at=(args.at if args.command == "advance" else None),
        )
    if args.command == "prepare-task-transition":
        plan = build_task_transition_plan(
            root,
            args.transition_id,
            args.transition_kind,
            args.prospective_ref,
        )
        published = publish_task_transition_plan(root, plan)
        return {
            "ok": True,
            "command": "prepare-task-transition",
            "plan": plan,
            **published,
        }
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
