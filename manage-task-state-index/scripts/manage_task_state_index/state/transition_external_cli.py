"""CLI adapter for externally settled task-state transitions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .transition_plan import settle_transition_external


def external_prepare_from_args(
    args: argparse.Namespace,
) -> dict[str, str] | None:
    ref = args.external_prepare_ref
    digest = args.external_prepare_sha256
    if bool(ref) != bool(digest):
        raise ValueError("External prepare requires both ref and SHA-256")
    return {"ref": ref, "sha256": digest} if ref else None


def _settle(args: argparse.Namespace) -> None:
    try:
        result = settle_transition_external(
            Path(args.root),
            args.plan,
            {"ref": args.external_commit_ref, "sha256": args.external_commit_sha256},
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def register_external_settlement_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "settle-plan-external",
        help="Settle a prospective task-state plan from a committed publication.",
    )
    parser.add_argument("--plan", required=True)
    parser.add_argument("--external-commit-ref", required=True)
    parser.add_argument("--external-commit-sha256", required=True)
    parser.set_defaults(func=_settle)


__all__ = (
    "external_prepare_from_args",
    "register_external_settlement_parser",
)
