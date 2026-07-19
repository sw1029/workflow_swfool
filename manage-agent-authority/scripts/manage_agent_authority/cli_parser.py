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
    group.add_argument("--compiled-operation")
    group.add_argument("--request")
    parser.add_argument("--context")


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


def build_parser(handlers: dict[str, Handler]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage deterministic authority v2 grants and leases."
    )
    subs = parser.add_subparsers(dest="command", required=True)
    _compilation(subs, handlers)

    snapshot_policy = subs.add_parser("snapshot-policy")
    _root(snapshot_policy)
    snapshot_policy.add_argument(
        "--policy-ref", default=".agent_goal/agent_authority.md"
    )
    snapshot_policy.add_argument("--expected-version", type=int, required=True)
    snapshot_policy.set_defaults(func=handlers["snapshot_policy"])

    snapshot_source = subs.add_parser("snapshot-source")
    _root(snapshot_source)
    snapshot_source.add_argument("--source-ref", required=True)
    snapshot_source.set_defaults(func=handlers["snapshot_source"])

    register = subs.add_parser("register-grant")
    _root(register)
    register.add_argument("--grant", required=True)
    register.set_defaults(func=handlers["register_grant"])

    delegate = subs.add_parser("delegate")
    _root(delegate)
    delegate.add_argument("--parent-grant-id", required=True)
    delegate.add_argument("--grant", required=True)
    delegate.set_defaults(func=handlers["delegate"])

    evaluate = subs.add_parser("evaluate")
    _root(evaluate)
    _at(evaluate)
    _skills_root(evaluate)
    _operation_input(evaluate)
    evaluate.set_defaults(func=handlers["evaluate"])

    compose = subs.add_parser("compose")
    _root(compose)
    compose.add_argument("--composition", required=True)
    compose.set_defaults(func=handlers["compose"])

    reserve = subs.add_parser("reserve")
    _root(reserve)
    _at(reserve)
    _skills_root(reserve)
    reserve.add_argument("--decision-ref", required=True)
    reserve.add_argument("--decision-sha256", required=True)
    reserve.add_argument("--idempotency-key", required=True)
    reserve.set_defaults(func=handlers["reserve"])

    verify = subs.add_parser("verify")
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

    consume = subs.add_parser("consume")
    _root(consume)
    _at(consume)
    _skills_root(consume)
    consume.add_argument("--reservation-ref", required=True)
    consume.add_argument("--reservation-sha256", required=True)
    consume.add_argument("--execution-result", required=True)
    consume.add_argument("--pre-commit-verification", required=True)
    consume.add_argument("--expected-subject-after-sha256", required=True)
    consume.add_argument("--expected-version", type=int, required=True)
    consume.add_argument("--idempotency-key", required=True)
    consume.set_defaults(func=handlers["consume"])

    release = subs.add_parser("release")
    _root(release)
    _at(release)
    release.add_argument("--reservation-ref", required=True)
    release.add_argument("--reservation-sha256", required=True)
    release.add_argument("--no-effect-evidence", required=True)
    release.add_argument("--expected-version", type=int, required=True)
    release.add_argument("--idempotency-key", required=True)
    release.add_argument(
        "--effect-status",
        choices=("not_started", "verified_no_effect", "unknown_effect"),
        required=True,
    )
    release.set_defaults(func=handlers["release"])

    _reconciliation(subs, handlers)

    recovery = subs.add_parser("prepare-source-recovery")
    _root(recovery)
    _at(recovery)
    _skills_root(recovery)
    recovery.add_argument("--decision-ref", required=True)
    recovery.add_argument("--decision-sha256", required=True)
    recovery.set_defaults(func=handlers["prepare_source_recovery"])

    transition = subs.add_parser("transition")
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

    status = subs.add_parser("status")
    _root(status)
    _skills_root(status)
    _at(status, required=False)
    status.add_argument("--grant-id")
    status.add_argument("--request-sha256")
    status.set_defaults(func=handlers["status"])

    resolve = subs.add_parser("resolve")
    _root(resolve)
    _at(resolve)
    _skills_root(resolve)
    _operation_input(resolve)
    resolve.set_defaults(func=handlers["resolve"])
    return parser


__all__ = ["build_parser"]
