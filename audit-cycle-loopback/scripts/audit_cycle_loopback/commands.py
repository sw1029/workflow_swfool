"""Static command registry for module invocation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import MappingProxyType


CommandHandler = Callable[[Sequence[str]], int]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str
    handler: CommandHandler


def _evaluate(arguments: Sequence[str]) -> int:
    from . import main

    return main(list(arguments))


COMMANDS = (
    CommandSpec(
        name="evaluate",
        help="Compute a conservative prepare-only loopback packet.",
        handler=_evaluate,
    ),
)


def _index_commands(specs: Sequence[CommandSpec]) -> MappingProxyType[str, CommandSpec]:
    index: dict[str, CommandSpec] = {}
    for spec in specs:
        name = spec.name.strip()
        if not name:
            raise ValueError("loopback command name must not be empty")
        if name in index:
            raise ValueError(f"duplicate loopback command: {name}")
        index[name] = spec
    return MappingProxyType(index)


COMMAND_INDEX = _index_commands(COMMANDS)


def _root_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m audit_cycle_loopback",
        description="Run audit-cycle-loopback commands.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=tuple(COMMAND_INDEX),
        help="Command to run.",
    )
    return parser


def dispatch(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = _root_parser()
    if not arguments:
        parser.print_help()
        return 0
    if arguments[0] in {"-h", "--help"}:
        parser.parse_args(arguments)
        return 0
    command = COMMAND_INDEX.get(arguments[0])
    if command is None:
        parser.error(
            f"invalid choice: {arguments[0]!r} "
            f"(choose from {', '.join(COMMAND_INDEX)})"
        )
    return command.handler(arguments[1:])


__all__ = (
    "COMMANDS",
    "COMMAND_INDEX",
    "CommandHandler",
    "CommandSpec",
    "dispatch",
)
