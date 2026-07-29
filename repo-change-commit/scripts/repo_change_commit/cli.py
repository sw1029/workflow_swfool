"""CLI for pre-commit anchor preparation and read-only HEAD verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .git_embedded_settlement import (
    GitEmbeddedSettlementError,
    validate_git_embedded_settlement,
)
from .git_observation import prepare_anchor, verify_head


def _json(value: str) -> dict[str, Any]:
    if value == "-":
        raw = sys.stdin.read()
    else:
        path = Path(value)
        raw = path.read_text(encoding="utf-8") if path.is_file() else value
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise GitEmbeddedSettlementError("JSON input must be an object")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m repo_change_commit")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-anchor")
    validate.add_argument("--input", required=True)
    prepare = commands.add_parser("prepare-anchor")
    prepare.add_argument("--root", default=".")
    prepare.add_argument("--anchor-path", required=True)
    prepare.add_argument("--message-file", required=True)
    prepare.add_argument("--intent", required=True)
    verify = commands.add_parser("verify-head")
    verify.add_argument("--root", default=".")
    verify.add_argument("--anchor-path", required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "validate-anchor":
        return validate_git_embedded_settlement(_json(args.input))
    if args.command == "prepare-anchor":
        return prepare_anchor(
            args.root,
            anchor_path=args.anchor_path,
            commit_message=Path(args.message_file).read_bytes(),
            intent=_json(args.intent),
        )
    return verify_head(args.root, anchor_path=args.anchor_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        output = _run(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


__all__ = ("main",)
