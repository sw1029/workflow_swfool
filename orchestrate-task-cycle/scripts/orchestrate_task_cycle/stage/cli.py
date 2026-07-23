"""CLI for deterministic orchestration stage preparation and submission."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .service import (
    advance_stage,
    execute_deterministic_stage,
    prepare_stage,
    submit_stage,
)
from .preparation_store import load_published_preparation, publish_preparation
from .input_compilers import (
    compile_routing,
    publish_owner_result,
    publish_semantic,
    publish_usage_observation,
)
from .specs import TARGET_COMPILE_SPECS


def _load_json(value: str) -> dict[str, Any]:
    if value == "-":
        raw = sys.stdin.read()
    elif value.lstrip().startswith("{"):
        raw = value
    else:
        path = Path(value)
        raw = path.read_text(encoding="utf-8") if path.is_file() else value
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("JSON input must be an object")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare, validate, and boundedly advance compiled cycle stages."
    )
    sub = parser.add_subparsers(dest="stage_command", required=True)
    prepare = sub.add_parser(
        "prepare", help="Compile a stage preparation; new cycles default to schema v3."
    )
    prepare.add_argument("--root", default=".")
    prepare.add_argument("--cycle-id", required=True)
    prepare.add_argument(
        "--target", required=True, choices=sorted(TARGET_COMPILE_SPECS)
    )
    prepare.add_argument(
        "--workflow-mode", choices=("normal", "bootstrap"), default="normal"
    )
    prepare.add_argument("--max-files", type=int, default=12)
    prepare.add_argument("--model-max-paths", type=int, default=40)
    prepare.add_argument(
        "--preparation-schema-version",
        type=int,
        choices=(1, 2, 3),
        help="Use 1/2 only when replaying a cycle initialized with that legacy protocol.",
    )
    prepare.add_argument("--publish", action="store_true")

    submit = sub.add_parser(
        "submit", help="Submit exact owner/semantic bindings to a compiled preparation."
    )
    submit.add_argument("--root", default=".")
    preparation_input = submit.add_mutually_exclusive_group(required=True)
    preparation_input.add_argument("--preparation")
    preparation_input.add_argument("--preparation-ref")
    submit.add_argument("--preparation-sha256")
    submit.add_argument(
        "--judgment", help="Inline judgment for schema-v1 compatibility only."
    )
    submit.add_argument("--owner-result-ref")
    submit.add_argument("--owner-result-sha256")
    submit.add_argument("--semantic-ref")
    submit.add_argument("--semantic-sha256")
    submit.add_argument("--routing-ref")
    submit.add_argument("--routing-sha256")
    submit.add_argument("--usage-ref")
    submit.add_argument("--usage-sha256")
    submit.add_argument("--deterministic-commit-ref")
    submit.add_argument("--deterministic-commit-sha256")
    submit.add_argument("--mode", choices=("block", "warn"), default="block")
    submit.add_argument("--apply", action="store_true")
    submit.add_argument("--max-files", type=int, default=12)
    submit.add_argument("--model-max-paths", type=int, default=40)

    advance = sub.add_parser(
        "advance", help="Advance deterministic stages until an owner boundary."
    )
    advance.add_argument("--root", default=".")
    advance.add_argument("--cycle-id", required=True)
    advance.add_argument(
        "--workflow-mode", choices=("normal", "bootstrap"), default="normal"
    )
    advance.add_argument("--max-steps", type=int, default=8)
    advance.add_argument("--apply", action="store_true")
    advance.add_argument("--max-files", type=int, default=12)
    advance.add_argument("--model-max-paths", type=int, default=40)
    advance.add_argument(
        "--preparation-schema-version",
        type=int,
        choices=(1, 2, 3),
        help="Use 1/2 only for a cycle already initialized with that protocol.",
    )
    execute = sub.add_parser(
        "execute", help="Run one allowlisted deterministic schema-v3 target only."
    )
    execute.add_argument("--root", default=".")
    execute.add_argument("--cycle-id", required=True)
    execute.add_argument(
        "--target", required=True, choices=sorted(TARGET_COMPILE_SPECS)
    )
    execute.add_argument(
        "--workflow-mode", choices=("normal", "bootstrap"), default="normal"
    )
    execute.add_argument("--apply", action="store_true")
    execute.add_argument("--max-files", type=int, default=12)
    execute.add_argument("--model-max-paths", type=int, default=40)
    execute.add_argument(
        "--preparation-schema-version", type=int, choices=(3,), default=3
    )
    owner = sub.add_parser(
        "publish-owner-result",
        help="Validate owner fields and publish a preparation-bound CAS wrapper.",
    )
    owner.add_argument("--root", default=".")
    owner.add_argument("--preparation-ref", required=True)
    owner.add_argument("--preparation-sha256", required=True)
    owner_input = owner.add_mutually_exclusive_group(required=True)
    owner_input.add_argument("--owner-result")
    owner_input.add_argument("--owner-result-ref")
    owner.add_argument("--owner-result-sha256")
    semantic = sub.add_parser(
        "publish-semantic",
        help="Validate hybrid semantic fields and publish a bound CAS wrapper.",
    )
    semantic.add_argument("--root", default=".")
    semantic.add_argument("--preparation-ref", required=True)
    semantic.add_argument("--preparation-sha256", required=True)
    semantic.add_argument("--semantic", required=True)
    semantic.add_argument("--reasoned-not-applicable")
    routing = sub.add_parser(
        "compile-routing",
        help="Compile routing semantics into a policy-derived bound receipt.",
    )
    routing.add_argument("--root", default=".")
    routing.add_argument("--preparation-ref", required=True)
    routing.add_argument("--preparation-sha256", required=True)
    routing.add_argument("--profile-id", required=True)
    routing.add_argument("--routing-request")
    usage = sub.add_parser(
        "publish-usage-observation",
        help="Publish unverified usage observations in a bound CAS wrapper.",
    )
    usage.add_argument("--root", default=".")
    usage.add_argument("--preparation-ref", required=True)
    usage.add_argument("--preparation-sha256", required=True)
    usage.add_argument("--observation", required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.stage_command == "publish-owner-result":
        if args.owner_result_ref and not args.owner_result_sha256:
            raise ValueError(
                "--owner-result-sha256 is required with --owner-result-ref"
            )
        if args.owner_result_sha256 and not args.owner_result_ref:
            raise ValueError(
                "--owner-result-sha256 is valid only with --owner-result-ref"
            )
        return publish_owner_result(
            args.root,
            args.preparation_ref,
            args.preparation_sha256,
            _load_json(args.owner_result) if args.owner_result else None,
            source_ref=args.owner_result_ref,
            source_sha256=args.owner_result_sha256,
        )
    if args.stage_command == "publish-semantic":
        return publish_semantic(
            args.root,
            args.preparation_ref,
            args.preparation_sha256,
            _load_json(args.semantic),
            reasoned_not_applicable=(
                _load_json(args.reasoned_not_applicable)
                if args.reasoned_not_applicable
                else None
            ),
        )
    if args.stage_command == "compile-routing":
        return compile_routing(
            args.root,
            args.preparation_ref,
            args.preparation_sha256,
            args.profile_id,
            (
                _load_json(args.routing_request)
                if args.routing_request
                else None
            ),
        )
    if args.stage_command == "publish-usage-observation":
        return publish_usage_observation(
            args.root,
            args.preparation_ref,
            args.preparation_sha256,
            _load_json(args.observation),
        )
    if args.stage_command == "prepare":
        prepared = prepare_stage(
            args.root,
            args.cycle_id,
            args.target,
            workflow_mode=args.workflow_mode,
            max_files=max(1, args.max_files),
            max_paths=max(1, args.model_max_paths),
            preparation_schema_version=args.preparation_schema_version,
            persist_compiler_artifacts=args.publish,
        )
        return publish_preparation(args.root, prepared) if args.publish else prepared
    if args.stage_command == "submit":
        if args.preparation_ref and not args.preparation_sha256:
            raise ValueError("--preparation-sha256 is required with --preparation-ref")
        if args.preparation_sha256 and not args.preparation_ref:
            raise ValueError(
                "--preparation-sha256 is valid only with --preparation-ref"
            )
        preparation = (
            load_published_preparation(
                args.root, args.preparation_ref, args.preparation_sha256
            )
            if args.preparation_ref
            else _load_json(args.preparation)
        )
        return submit_stage(
            args.root,
            preparation,
            _load_json(args.judgment) if args.judgment else None,
            mode=args.mode,
            apply=args.apply,
            max_files=max(1, args.max_files),
            max_paths=max(1, args.model_max_paths),
            owner_result_ref=args.owner_result_ref,
            owner_result_sha256=args.owner_result_sha256,
            semantic_ref=args.semantic_ref,
            semantic_sha256=args.semantic_sha256,
            routing_ref=args.routing_ref,
            routing_sha256=args.routing_sha256,
            usage_ref=args.usage_ref,
            usage_sha256=args.usage_sha256,
            deterministic_commit_ref=args.deterministic_commit_ref,
            deterministic_commit_sha256=args.deterministic_commit_sha256,
        )
    if args.stage_command == "execute":
        return execute_deterministic_stage(
            args.root,
            args.cycle_id,
            args.target,
            workflow_mode=args.workflow_mode,
            apply=args.apply,
            max_files=max(1, args.max_files),
            max_paths=max(1, args.model_max_paths),
            preparation_schema_version=args.preparation_schema_version,
        )
    return advance_stage(
        args.root,
        args.cycle_id,
        workflow_mode=args.workflow_mode,
        max_steps=args.max_steps,
        apply=args.apply,
        max_files=max(1, args.max_files),
        max_paths=max(1, args.model_max_paths),
        preparation_schema_version=args.preparation_schema_version,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        output = _run(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 2 if output.get("status") == "block" else 0


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
