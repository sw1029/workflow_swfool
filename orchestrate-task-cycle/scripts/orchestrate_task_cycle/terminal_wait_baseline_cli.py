"""CLI for authority-settled terminal-wait baseline publication."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .terminal_wait_baseline import (
    activate_terminal_wait_baseline,
    audit_terminal_wait_baseline,
    materialize_terminal_wait_authority_subject,
    prepare_terminal_wait_baseline,
    resolve_terminal_wait_baseline,
)
from .terminal_wait_baseline_contract import (
    binding,
    normalize_plan,
    subject_digest,
    validate_authority_subject_binding,
)
from .terminal_wait_baseline_store import MAX_ARTIFACT_BYTES, safe_regular_file


def _load_object(root: Path, ref: str, label: str) -> dict[str, Any]:
    try:
        path = safe_regular_file(root, ref, label)
        with path.open("rb") as handle:
            body = handle.read(MAX_ARTIFACT_BYTES + 1)
        if len(body) > MAX_ARTIFACT_BYTES:
            raise ValueError(f"{label} exceeds the artifact size limit")
        value = json.loads(body)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    commands = parser.add_subparsers(dest="action", required=True)
    subject = commands.add_parser("subject-digest")
    subject.add_argument("--plan", required=True)
    materialize = commands.add_parser("materialize-subject")
    materialize.add_argument("--subject", required=True)
    materialize.add_argument("--dry-run", action="store_true")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--plan", required=True)
    prepare.add_argument("--dry-run", action="store_true")
    activate = commands.add_parser("activate")
    activate.add_argument("--completion-ref", required=True)
    activate.add_argument("--completion-sha256", required=True)
    activate.add_argument("--use-receipt-ref", required=True)
    activate.add_argument("--use-receipt-sha256", required=True)
    commands.add_parser("resolve")
    commands.add_parser("audit")
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve(strict=True)
    if args.action == "subject-digest":
        plan = normalize_plan(_load_object(root, args.plan, "baseline plan"))
        identity = validate_authority_subject_binding(root, plan)
        return {
            "status": "ok",
            "subject_digest": subject_digest(plan),
            "authority_subject_binding": plan["authority_subject"],
            "authority_subject": identity,
            "mutation_performed": False,
        }
    if args.action == "materialize-subject":
        return materialize_terminal_wait_authority_subject(
            root,
            _load_object(root, args.subject, "baseline authority subject"),
            dry_run=args.dry_run,
        )
    if args.action == "prepare":
        return prepare_terminal_wait_baseline(
            root,
            _load_object(root, args.plan, "baseline plan"),
            dry_run=args.dry_run,
        )
    if args.action == "activate":
        return activate_terminal_wait_baseline(
            root,
            binding(
                {"ref": args.completion_ref, "sha256": args.completion_sha256},
                "completion binding",
            ),
            binding(
                {
                    "ref": args.use_receipt_ref,
                    "sha256": args.use_receipt_sha256,
                },
                "use-receipt binding",
            ),
        )
    if args.action == "resolve":
        return resolve_terminal_wait_baseline(root)
    return audit_terminal_wait_baseline(root)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "block", "error": str(exc), "mutation_performed": False}
        code = 2
    else:
        code = 0
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
