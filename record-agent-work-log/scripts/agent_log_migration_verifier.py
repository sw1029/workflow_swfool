#!/usr/bin/env python3
"""Read-only, source-separated verification of a sealed agent-log migration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from agent_log_migration_verifier_core import VerificationError, _load_json
from agent_log_migration_verifier_graph import (
    _boundary_observation_sha256,
    inspect_transaction_boundary,
    verify_migration,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Workspace or copied-fixture root")
    parser.add_argument("--receipt", required=True, help="Workspace-local committed receipt")
    parser.add_argument(
        "--expected-status-map",
        required=True,
        help="Caller-owned exact status map; must be byte-identical to the published copy",
    )
    parser.add_argument(
        "--expected-recovery-status",
        required=True,
        choices=("not_needed", "forward_completed"),
        help="Caller-owned expected recovery state; never inferred from the receipt",
    )
    parser.add_argument(
        "--recovery-observation",
        help="Independent pre-recovery boundary-observation JSON; required only for forward recovery",
    )
    parser.add_argument(
        "--expected-recovery-observation-sha256",
        help="Externally preserved hash emitted with the pre-recovery observation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        recovery_observation = None
        if args.recovery_observation:
            recovery_observation, _ = _load_json(
                Path(args.recovery_observation), "recovery boundary observation"
            )
        result = verify_migration(
            args.root,
            args.receipt,
            expected_status_map_raw=args.expected_status_map,
            expected_recovery_status=args.expected_recovery_status,
            recovery_observation=recovery_observation,
            expected_recovery_observation_sha256=(
                args.expected_recovery_observation_sha256
            ),
        )
    except (OSError, VerificationError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
