"""CLI adapters for compiler-first task-state owner operations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from .compiler_contract_lint import lint_owner_result
from .owner_validation import validate_owner_result
from .prevalidation_compiler import compile_prevalidation
from .scan_transition import apply_scan, prepare_scan
from .selected_successor import prepare_selected_successor
from .storage import jsonl_path, markdown_path, now_iso


def _binding(ref: str, digest: str) -> dict[str, str]:
    return {"ref": ref, "sha256": digest}


def _focus(args: argparse.Namespace) -> dict[str, str] | None:
    ref, digest = args.focus_ref, args.focus_sha256
    if (ref is None) != (digest is None):
        raise SystemExit("--focus-ref and --focus-sha256 must be supplied together")
    return _binding(ref, digest) if ref is not None else None


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_prepare_scan(args: argparse.Namespace) -> None:
    try:
        result = prepare_scan(
            Path(args.root), at=args.at, focus=_focus(args), publish=not args.dry_run
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _print(result)


def cmd_apply_scan(args: argparse.Namespace) -> None:
    try:
        result = apply_scan(
            Path(args.root), _binding(args.compilation_ref, args.compilation_sha256)
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _print(result)


def cmd_prepare_selected_successor(args: argparse.Namespace) -> None:
    try:
        result = prepare_selected_successor(
            Path(args.root),
            source_decision=_binding(
                args.source_decision_ref, args.source_decision_sha256
            ),
            task_source=_binding(args.task_source_ref, args.task_source_sha256),
            at=args.at,
            publish=not args.dry_run,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _print(result)


def cmd_validate_owner_result(args: argparse.Namespace) -> None:
    try:
        result = validate_owner_result(
            Path(args.root),
            owner_result=_binding(args.owner_result_ref, args.owner_result_sha256),
            reservation=_binding(args.reservation_ref, args.reservation_sha256),
            pre_commit_verification=_binding(
                args.pre_commit_ref, args.pre_commit_sha256
            ),
            phase=args.phase,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _print(result)


def cmd_lint_owner_result(args: argparse.Namespace) -> None:
    try:
        result = lint_owner_result(
            Path(args.root),
            owner_result=_binding(
                args.owner_result_ref, args.owner_result_sha256
            ),
            cycle_id=args.cycle_id,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _print(result)
    if result["lint_status"] == "block":
        raise SystemExit(2)


def cmd_compile_prevalidation(args: argparse.Namespace) -> None:
    try:
        result = compile_prevalidation(
            Path(args.root),
            at=args.at,
            publish=not args.dry_run,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _print(result)


def run_scan_command(
    args: argparse.Namespace,
    legacy_scan: Callable[..., dict[str, Any]],
) -> int:
    """Keep legacy read-only output while routing effects through one batch."""

    root = Path(args.root).resolve()
    read_only = bool(getattr(args, "dry_run", False) or getattr(args, "check", False))
    if read_only or (
        not jsonl_path(root).is_file() and not markdown_path(root).is_file()
        and not (root / "task.md").is_file() and not (root / ".task").exists()
    ):
        result = legacy_scan(root, dry_run=read_only)
        result["mode"] = "check" if getattr(args, "check", False) else result["mode"]
        _print(result)
        return 1 if getattr(args, "check", False) and result.get("would_change") else 0
    prepared = prepare_scan(root, at=now_iso(), publish=True)
    applied = apply_scan(root, prepared["compilation_binding"])
    _print({
        "mode": "apply",
        "mutation_performed": applied["mutation_performed"],
        "indexed_events": applied["event_count"],
        "events": [],
        "planned_artifact_updates": applied["logical_update_count"],
        "focus_results": applied["focus_results"],
        "owner_result_binding": applied["owner_result_binding"],
        "scan_evidence_status": "evaluated",
    })
    return 0


def register_compiler_parsers(subparsers: Any) -> None:
    prepare = subparsers.add_parser(
        "prepare-scan", help="Compile and optionally publish one full scan batch."
    )
    prepare.add_argument("--at", required=True)
    prepare.add_argument("--focus-ref")
    prepare.add_argument("--focus-sha256")
    prepare.add_argument("--dry-run", action="store_true")
    prepare.set_defaults(func=cmd_prepare_scan)

    apply = subparsers.add_parser(
        "apply-scan", help="Apply one exact scan compilation in one batch."
    )
    apply.add_argument("--compilation-ref", required=True)
    apply.add_argument("--compilation-sha256", required=True)
    apply.set_defaults(func=cmd_apply_scan)

    lint = subparsers.add_parser(
        "lint-owner-result",
        help="Bound-check one task-state owner-result compiler contract.",
    )
    lint.add_argument("--owner-result-ref", required=True)
    lint.add_argument("--owner-result-sha256", required=True)
    lint.add_argument("--cycle-id", required=True)
    lint.set_defaults(func=cmd_lint_owner_result)

    prevalidation = subparsers.add_parser(
        "compile-prevalidation",
        help="Compile one exact task-index prevalidation owner result.",
    )
    prevalidation.add_argument("--at", required=True)
    prevalidation.add_argument("--dry-run", action="store_true")
    prevalidation.set_defaults(func=cmd_compile_prevalidation)

    successor = subparsers.add_parser(
        "prepare-selected-successor",
        help="Render a prospective selected-successor task-state plan.",
    )
    successor.add_argument("--source-decision-ref", required=True)
    successor.add_argument("--source-decision-sha256", required=True)
    successor.add_argument("--task-source-ref", required=True)
    successor.add_argument("--task-source-sha256", required=True)
    successor.add_argument("--at", required=True)
    successor.add_argument("--dry-run", action="store_true")
    successor.set_defaults(func=cmd_prepare_selected_successor)

    validate = subparsers.add_parser(
        "validate-owner-result",
        help="Validate a task-state owner result for authority settlement.",
    )
    for name in (
        "owner-result-ref", "owner-result-sha256", "reservation-ref",
        "reservation-sha256", "pre-commit-ref", "pre-commit-sha256",
    ):
        validate.add_argument(f"--{name}", required=True)
    validate.add_argument("--phase", choices=("current", "historical"), default="current")
    validate.set_defaults(func=cmd_validate_owner_result)


__all__ = ("register_compiler_parsers", "run_scan_command")
