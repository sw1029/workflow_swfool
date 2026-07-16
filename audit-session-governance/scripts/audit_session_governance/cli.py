"""Static module command registry for session governance."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable, Sequence


Handler = Callable[[list[str] | None], int]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    handler: Handler


def _capture(argv: list[str] | None) -> int:
    from .capture_projection import main

    return main(argv)


def _audit(argv: list[str] | None) -> int:
    from .session_audit import main

    return main(argv)


COMMANDS = (
    CommandSpec("capture", _capture),
    CommandSpec("audit", _audit),
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m audit_session_governance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    specs = {spec.name: spec for spec in COMMANDS}
    if len(specs) != len(COMMANDS):
        raise RuntimeError("duplicate session-governance module command")
    for spec in COMMANDS:
        subparsers.add_parser(spec.name, add_help=False)
    args, remainder = parser.parse_known_args(argv)
    return specs[args.command].handler(remainder)
