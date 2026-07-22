"""CLI transport for repository-owned workflow adapter scan and handoff."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Sequence

from .repo_skill_adapter import (
    _load_scan,
    registered_adapter_handoff,
    scan_repo_skill_adapters,
)


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("--root", default=".")
    scan.add_argument("--cycle-id", default="unknown")
    scan.add_argument("--output")
    handoff = commands.add_parser("handoff")
    handoff.add_argument("--root", default=".")
    handoff.add_argument("--scan-json", required=True)
    handoff.add_argument("--phase", required=True)
    handoff.add_argument("--consumer-id", required=True)
    handoff.add_argument("--output")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).expanduser().resolve(strict=True)
    if args.command == "scan":
        result = scan_repo_skill_adapters(root, cycle_id=args.cycle_id)
    else:
        result = registered_adapter_handoff(
            root,
            _load_scan(root, args.scan_json),
            phase=args.phase,
            consumer_id=args.consumer_id,
        )
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        _write(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return (
        0
        if result.get("status")
        not in {"invalid_scan", "ambiguous", "registered_unavailable"}
        else 2
    )


__all__ = ("main",)
