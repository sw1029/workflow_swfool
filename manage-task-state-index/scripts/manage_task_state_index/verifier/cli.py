#!/usr/bin/env python3
"""Read-only, source-separated verification of a sealed task-state migration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True

from .core import (
    VERIFICATION_ERROR_CODES,
    VerificationError,
    _load_json,
)
from .graph import (
    _boundary_observation_sha256,
    inspect_transaction_boundary,
    verify_migration,
)

__all__ = [
    "VerificationError",
    "_boundary_observation_sha256",
    "inspect_transaction_boundary",
    "verify_migration",
]


def _failure_json(error_code: str) -> str:
    safe_code = (
        error_code
        if error_code in VERIFICATION_ERROR_CODES
        else "internal_verification_failure"
    )
    return json.dumps(
        {"status": "fail", "error_code": safe_code},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _error_code(exc: Exception) -> str:
    if isinstance(exc, VerificationError):
        return exc.error_code
    if isinstance(exc, OSError):
        return "io_failure"
    if isinstance(exc, (TypeError, KeyError, AttributeError, ValueError)):
        return "invalid_verification_input"
    return "internal_verification_failure"


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        print(_failure_json("arguments_invalid"))
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Workspace or relocated copied-fixture root")
    parser.add_argument("--receipt", required=True, help="Workspace-local committed receipt")
    parser.add_argument(
        "--expected-mapping-manifest",
        required=True,
        help="Caller-owned exact mapping/status expectation outside every transaction tree",
    )
    parser.add_argument(
        "--expected-recovery-status",
        required=True,
        choices=("not_required", "forward_completed"),
        help="Caller-owned expected recovery state; never inferred from producer claims",
    )
    parser.add_argument(
        "--recovery-observation",
        help="Independent pre-recovery boundary observation; required for forward recovery",
    )
    parser.add_argument(
        "--expected-recovery-observation-sha256",
        help="Externally preserved SHA-256 of the pre-recovery observation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        observation = None
        if args.recovery_observation:
            observation, _payload = _load_json(
                Path(args.recovery_observation), "recovery boundary observation"
            )
        result = verify_migration(
            args.root,
            args.receipt,
            expected_mapping_raw=args.expected_mapping_manifest,
            expected_recovery_status=args.expected_recovery_status,
            recovery_observation=observation,
            expected_recovery_observation_sha256=args.expected_recovery_observation_sha256,
        )
    except Exception as exc:
        print(_failure_json(_error_code(exc)))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
