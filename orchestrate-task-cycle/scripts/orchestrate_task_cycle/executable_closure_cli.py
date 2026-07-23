from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .executable_closure import (
    ARTIFACT_KIND,
    INVALID,
    READY,
    SCHEMA_VERSION,
    preflight_executable_closure,
)
from .selection_decision_store import normalize_binding


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only executable-closure preflight."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--operation-batch-ref", required=True)
    parser.add_argument("--operation-batch-sha256", required=True)
    parser.add_argument("--selected-successor-bundle-ref")
    parser.add_argument("--selected-successor-bundle-sha256")
    parser.add_argument(
        "--authority-decision-ref",
        action="append",
        default=[],
        help="repeat with one matching --authority-decision-sha256",
    )
    parser.add_argument(
        "--authority-decision-sha256",
        action="append",
        default=[],
    )
    return parser


def _bundle_binding(args: argparse.Namespace) -> dict[str, str] | None:
    ref = args.selected_successor_bundle_ref
    digest = args.selected_successor_bundle_sha256
    if bool(ref) != bool(digest):
        raise ValueError("selected-successor bundle requires both ref and SHA-256")
    return {"ref": ref, "sha256": digest} if ref else None


def _decision_bindings(args: argparse.Namespace) -> list[dict[str, str]]:
    refs = args.authority_decision_ref
    digests = args.authority_decision_sha256
    if len(refs) != len(digests):
        raise ValueError("authority decisions require matching ref and SHA-256 counts")
    return [
        normalize_binding(
            {"ref": ref, "sha256": digest},
            f"authority decision[{index}]",
        )
        for index, (ref, digest) in enumerate(zip(refs, digests, strict=True))
    ]


def _run(args: argparse.Namespace) -> dict[str, Any]:
    return preflight_executable_closure(
        Path(args.root),
        {
            "ref": args.operation_batch_ref,
            "sha256": args.operation_batch_sha256,
        },
        selected_successor_bundle_binding=_bundle_binding(args),
        decision_bindings=_decision_bindings(args),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(args)
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        SystemExit,
    ) as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "artifact_kind": ARTIFACT_KIND,
            "status": INVALID,
            "error": str(exc),
            "mutation_performed": False,
        }
        code = 2
    else:
        code = 0 if result["status"] == READY else 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
