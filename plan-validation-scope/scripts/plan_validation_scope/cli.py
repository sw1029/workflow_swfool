"""Static module command registry for validation-scope operations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable, Sequence


Handler = Callable[[list[str] | None], int]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    handler: Handler
    prefix: tuple[str, ...] = ()


def _changed_surface(argv: list[str] | None) -> int:
    from .changed_surface import main

    return main(argv)


def _validation_scope(argv: list[str] | None) -> int:
    from .validation_scope import main

    return main(argv)


COMMANDS = (
    CommandSpec("changed-surface", _changed_surface),
    CommandSpec("plan", _validation_scope, ("--mode", "plan")),
    CommandSpec("finalize", _validation_scope, ("--mode", "finalize")),
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m plan_validation_scope")
    subparsers = parser.add_subparsers(dest="command", required=True)
    specs = {spec.name: spec for spec in COMMANDS}
    if len(specs) != len(COMMANDS):
        raise RuntimeError("duplicate validation-scope module command")
    for spec in COMMANDS:
        subparsers.add_parser(spec.name, add_help=False)
    args, remainder = parser.parse_known_args(argv)
    spec = specs[args.command]
    return spec.handler([*remainder, *spec.prefix])
