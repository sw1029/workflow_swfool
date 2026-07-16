#!/usr/bin/env python3
"""Create and validate body-free, non-authoritative session audit packets."""

from __future__ import annotations

import argparse
import json
import sys

from .session_common import (
    AuditError,
    MAX_BYTES,
    MAX_LINES as MAX_LINES,
    TOOLS,
    derived_id as derived_id,
    digest as digest,
)
from .session_packets import validate_packet as validate_packet
from .session_service import auto_rebuild_index, inspect, rebuild_index, validate_file

def cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = commands.add_parser("inspect")
    inspect_cmd.add_argument("--root", required=True)
    inspect_cmd.add_argument("--source", required=True)
    inspect_cmd.add_argument("--tool", required=True, choices=sorted(TOOLS))
    inspect_cmd.add_argument("--session-id")
    inspect_cmd.add_argument("--cycle-id")
    inspect_cmd.add_argument("--task-id")
    inspect_cmd.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    validate_cmd = commands.add_parser("validate")
    validate_cmd.add_argument("--root", required=True)
    validate_cmd.add_argument("--packet", required=True)
    index_cmd = commands.add_parser("rebuild-index")
    index_cmd.add_argument("--root", required=True)
    auto_index_cmd = commands.add_parser("auto-rebuild-index")
    auto_index_cmd.add_argument("--root", required=True)
    auto_index_cmd.add_argument("--mode-resolution", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = cli_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            packet, output = inspect(
                args.root, args.source, tool=args.tool,
                session_id=args.session_id, cycle_id=args.cycle_id,
                task_id=args.task_id, max_bytes=args.max_bytes,
            )
            result = {
                "audit_id": packet["audit_id"],
                "capture_status": packet["capture_status"],
                "consumable": packet["consumable"],
                "output": str(output),
            }
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0
        if args.command == "validate":
            packet, errors = validate_file(args.root, args.packet)
            print(json.dumps({
                "audit_id": packet.get("audit_id"),
                "valid": not errors,
                "errors": errors,
            }, sort_keys=True, separators=(",", ":")))
            return 0 if not errors else 2
        if args.command == "auto-rebuild-index":
            receipt, output = auto_rebuild_index(
                args.root,
                args.mode_resolution,
            )
            print(json.dumps({**receipt, "output": str(output)}, sort_keys=True, separators=(",", ":")))
            return 0
        index, output = rebuild_index(args.root)
        print(json.dumps({
            "index_id": index["index_id"],
            "entry_count": len(index["entries"]),
            "output": str(output),
        }, sort_keys=True, separators=(",", ":")))
        return 0
    except AuditError as exc:
        print(f"session_audit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
