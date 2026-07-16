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


def _receipt(argv: list[str] | None) -> int:
    from .authority_receipt import main

    return main(argv)


COMMANDS = (CommandSpec("receipt", _receipt),)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m manage_agent_authority")
    subparsers = parser.add_subparsers(dest="command", required=True)
    specs = {spec.name: spec for spec in COMMANDS}
    if len(specs) != len(COMMANDS):
        raise RuntimeError("duplicate authority module command")
    for spec in COMMANDS:
        subparsers.add_parser(spec.name, add_help=False)
    args, remainder = parser.parse_known_args(argv)
    return specs[args.command].handler(remainder)
