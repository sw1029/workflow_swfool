from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from typing import Sequence


Handler = Callable[[list[str] | None], int]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    handler: Handler


def _failure_autopsy(argv: list[str] | None) -> int:
    from .safe_failure_autopsy import main

    return main(argv)

def _terminal_projection(argv: list[str] | None) -> int:
    import argparse
    import json
    import sys

    from .terminal_projection import (
        publish_run_terminal_projection,
        validate_run_terminal_projection,
    )

    parser = argparse.ArgumentParser(
        prog="python3 -m run_task_code_and_log terminal-projection"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    if args.input == "-":
        raw = sys.stdin.read()
    else:
        path = Path(args.input)
        raw = path.read_text(encoding="utf-8") if path.is_file() else args.input
    try:
        value = json.loads(raw)
        projection = validate_run_terminal_projection(value)
        output = (
            publish_run_terminal_projection(args.root, projection)
            if args.publish
            else projection
        )
    except (ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


COMMANDS = (
    CommandSpec("failure-autopsy", _failure_autopsy),
    CommandSpec("terminal-projection", _terminal_projection),
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m run_task_code_and_log")
    subparsers = parser.add_subparsers(dest="command", required=True)
    specs = {spec.name: spec for spec in COMMANDS}
    if len(specs) != len(COMMANDS):
        raise RuntimeError("duplicate run-log module command")
    for spec in COMMANDS:
        subparsers.add_parser(spec.name, add_help=False)
    args, remainder = parser.parse_known_args(argv)
    return specs[args.command].handler(remainder)
