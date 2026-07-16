from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable
from typing import Sequence


Handler = Callable[[list[str] | None], int]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    handler: Handler


def _collect_evidence(argv: list[str] | None) -> int:
    from .collect_completion_evidence import main

    return main(argv)


COMMANDS = (CommandSpec("collect-evidence", _collect_evidence),)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m validate_task_completion")
    subparsers = parser.add_subparsers(dest="command", required=True)
    specs = {spec.name: spec for spec in COMMANDS}
    if len(specs) != len(COMMANDS):
        raise RuntimeError("duplicate completion module command")
    for spec in COMMANDS:
        subparsers.add_parser(spec.name, add_help=False)
    args, remainder = parser.parse_known_args(argv)
    return specs[args.command].handler(remainder)
