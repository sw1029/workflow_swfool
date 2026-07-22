"""Argument parser isolated from authority command implementations."""

from __future__ import annotations

import argparse
from typing import Any, Callable


Handler = Callable[[argparse.Namespace], int]


def _root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".")


def _at(parser: argparse.ArgumentParser, *, required: bool = True) -> None:
    parser.add_argument(
        "--at", required=required,
        help="RFC3339 time with timezone" if required else
        "RFC3339 evaluation time with timezone; defaults to current UTC time",
    )


def _skills_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skills-root")


def _operation_input(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--compiled-operation",
        help="Preferred exact binding emitted by compile-operation.",
    )
    group.add_argument(
        "--request",
        help="Legacy compatibility/contract diagnostics only: full request JSON.",
    )
    parser.add_argument(
        "--context",
        help="Legacy compatibility/contract diagnostics only: full context JSON.",
    )


def _compilation(subparsers: Any, handlers: dict[str, Handler]) -> None:
    parser = subparsers.add_parser("compile-operation")
    _root(parser)
    _at(parser)
    _skills_root(parser)
    parser.add_argument(
        "--seed", required=True, help="JSON object, JSON file, or - for stdin"
    )
    parser.add_argument(
        "--publish", action="store_true",
        help="immutably publish the non-authoritative compilation and emit its binding",
    )
    parser.set_defaults(func=handlers["compile_operation"])


def _reconciliation(subparsers: Any, handlers: dict[str, Handler]) -> None:
    reconcile = subparsers.add_parser("reconcile")
    _root(reconcile)
    _at(reconcile)
    reconcile.add_argument("--reservation-ref", required=True)
    reconcile.add_argument("--reservation-sha256", required=True)
    reconcile.add_argument("--effect-evidence", required=True)
    reconcile.add_argument("--pre-commit-verification")
    reconcile.add_argument("--expected-version", type=int, required=True)
    reconcile.add_argument("--idempotency-key", required=True)
    reconcile.add_argument(
        "--outcome",
        choices=("confirmed_effect", "confirmed_no_effect", "still_unknown"),
        required=True,
    )
    reconcile.set_defaults(func=handlers["reconcile"])

    evidence = subparsers.add_parser("prepare-reconciliation-evidence")
    _root(evidence)
    _at(evidence)
    evidence.add_argument("--reservation-ref", required=True)
    evidence.add_argument("--reservation-sha256", required=True)
    evidence.add_argument("--owner-result")
    evidence.add_argument("--expected-version", type=int, required=True)
    evidence.add_argument(
        "--outcome",
        choices=("confirmed_effect", "confirmed_no_effect", "still_unknown"),
        required=True,
    )
    evidence.set_defaults(func=handlers["prepare_reconciliation_evidence"])


def _policy_registration(subparsers: Any, handlers: dict[str, Handler]) -> None:
    snapshot_policy = subparsers.add_parser("snapshot-policy")
    _root(snapshot_policy)
    snapshot_policy.add_argument(
        "--policy-ref", default=".agent_goal/agent_authority.md"
    )
    snapshot_policy.add_argument("--expected-version", type=int, required=True)
    snapshot_policy.set_defaults(func=handlers["snapshot_policy"])

    snapshot_source = subparsers.add_parser("snapshot-source")
    _root(snapshot_source)
    snapshot_source.add_argument("--source-ref", required=True)
    snapshot_source.set_defaults(func=handlers["snapshot_source"])

    register = subparsers.add_parser("register-grant")
    _root(register)
    register.add_argument("--grant", required=True)
    register.set_defaults(func=handlers["register_grant"])

    delegate = subparsers.add_parser("delegate")
    _root(delegate)
    delegate.add_argument("--parent-grant-id", required=True)
    delegate.add_argument("--grant", required=True)
    delegate.set_defaults(func=handlers["delegate"])


def _evaluation(subparsers: Any, handlers: dict[str, Handler]) -> None:
    evaluate = subparsers.add_parser("evaluate")
    _root(evaluate)
    _at(evaluate)
    _skills_root(evaluate)
    _operation_input(evaluate)
    evaluate.set_defaults(func=handlers["evaluate"])

    compose = subparsers.add_parser("compose")
    _root(compose)
    compose.add_argument("--composition", required=True)
    compose.set_defaults(func=handlers["compose"])

def _lifecycle(subparsers: Any, handlers: dict[str, Handler]) -> None:
    reserve = subparsers.add_parser("reserve")
    _root(reserve)
    _at(reserve)
    _skills_root(reserve)
    reserve.add_argument("--decision-ref", required=True)
    reserve.add_argument("--decision-sha256", required=True)
    reserve.add_argument("--idempotency-key", required=True)
    reserve.set_defaults(func=handlers["reserve"])

    verify = subparsers.add_parser("verify")
    _root(verify)
    _at(verify)
    _skills_root(verify)
    verify.add_argument("--reservation-ref", required=True)
    verify.add_argument("--reservation-sha256", required=True)
    verify.add_argument("--expected-version", type=int, required=True)
    verify.add_argument(
        "--stage", choices=("pre_dispatch", "pre_commit"), required=True
    )
    verify.set_defaults(func=handlers["verify"])

    consume = subparsers.add_parser(
        "consume",
        help="Unregistered schema-v2 compatibility only; registered owners use settle.",
    )
    _root(consume)
    _at(consume)
    _skills_root(consume)
    consume.add_argument("--reservation-ref", required=True)
    consume.add_argument("--reservation-sha256", required=True)
    consume.add_argument(
        "--execution-result",
        required=True,
        help="Unregistered schema-v2 compatibility result; registered owners use settle.",
    )
    consume.add_argument("--pre-commit-verification", required=True)
    consume.add_argument("--expected-subject-after-sha256", required=True)
    consume.add_argument("--expected-version", type=int, required=True)
    consume.add_argument("--idempotency-key", required=True)
    consume.set_defaults(func=handlers["consume"])

    settle = subparsers.add_parser(
        "settle",
        help="Validate an exact owner result and consume, release, or quarantine.",
    )
    _root(settle)
    _at(settle)
    _skills_root(settle)
    settle.add_argument("--reservation-ref", required=True)
    settle.add_argument("--reservation-sha256", required=True)
    settle.add_argument("--owner-result", required=True)
    settle.add_argument("--pre-commit-verification", required=True)
    settle.add_argument("--expected-version", type=int, required=True)
    settle.add_argument("--idempotency-key", required=True)
    settle.set_defaults(func=handlers["settle"])

    release = subparsers.add_parser(
        "release",
        help="Unregistered compatibility only; registered owner release is forbidden.",
    )
    _root(release)
    _at(release)
    release.add_argument("--reservation-ref", required=True)
    release.add_argument("--reservation-sha256", required=True)
    release.add_argument(
        "--no-effect-evidence",
        required=True,
        help="Unregistered compatibility evidence; registered owners use settle.",
    )
    release.add_argument("--expected-version", type=int, required=True)
    release.add_argument("--idempotency-key", required=True)
    release.add_argument(
        "--effect-status",
        choices=("not_started", "verified_no_effect", "unknown_effect"),
        required=True,
    )
    release.set_defaults(func=handlers["release"])


def _recovery_and_status(
    subparsers: Any, handlers: dict[str, Handler]
) -> None:
    recovery = subparsers.add_parser("prepare-source-recovery")
    _root(recovery)
    _at(recovery)
    _skills_root(recovery)
    recovery.add_argument("--decision-ref", required=True)
    recovery.add_argument("--decision-sha256", required=True)
    recovery.set_defaults(func=handlers["prepare_source_recovery"])

    materialize = subparsers.add_parser(
        "materialize-approved-recovery",
        help="Render exact source/grant artifacts from an external user decision.",
    )
    _root(materialize)
    _skills_root(materialize)
    materialize.add_argument("--recovery-recipe", required=True)
    materialize.add_argument("--user-decision", required=True)
    materialize.set_defaults(func=handlers["materialize_approved_recovery"])

    transition = subparsers.add_parser("transition")
    _root(transition)
    _at(transition)
    transition.add_argument("--grant-id", required=True)
    transition.add_argument(
        "--transition",
        choices=("revoked", "suspended", "expired", "reactivated"),
        required=True,
    )
    transition.add_argument("--event-id", required=True)
    transition.add_argument("--expected-version", type=int, required=True)
    transition.add_argument("--source-approval", required=True)
    transition.set_defaults(func=handlers["transition"])

    status = subparsers.add_parser("status")
    _root(status)
    _skills_root(status)
    _at(status, required=False)
    status.add_argument("--grant-id")
    status.add_argument("--request-sha256")
    status.set_defaults(func=handlers["status"])

    resolve = subparsers.add_parser("resolve")
    _root(resolve)
    _at(resolve)
    _skills_root(resolve)
    _operation_input(resolve)
    resolve.set_defaults(func=handlers["resolve"])


def build_parser(handlers: dict[str, Handler]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage deterministic authority v2 grants and leases."
    )
    subs = parser.add_subparsers(dest="command", required=True)
    _compilation(subs, handlers)
    _policy_registration(subs, handlers)
    _evaluation(subs, handlers)
    _lifecycle(subs, handlers)
    _reconciliation(subs, handlers)
    _recovery_and_status(subs, handlers)
    return parser


__all__ = ["build_parser"]
