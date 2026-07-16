"""Static command registry for the external-advice module entry point."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Callable, Sequence


CommandHandler = Callable[[list[str] | None], int]


@dataclass(frozen=True)
class CommandSpec:
    """One explicitly owned command and its lazy callable handler."""

    name: str
    handler: CommandHandler
    help: str


def _registry_handler(argv: list[str] | None) -> int:
    from .registry import main

    return int(main(argv) or 0)


COMMANDS = (
    CommandSpec("registry", _registry_handler, "Manage the external-advice registry."),
)
COMMAND_BY_NAME = {command.name: command for command in COMMANDS}
if len(COMMAND_BY_NAME) != len(COMMANDS):  # pragma: no cover - static invariant
    raise RuntimeError("duplicate external-advice command")


def _usage() -> str:
    return "usage: python3 -m manage_external_advice {registry} ..."


def _help() -> str:
    lines = [_usage(), "", "commands:"]
    lines.extend(f"  {command.name:<18} {command.help}" for command in COMMANDS)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch one public command without importing unrelated implementations."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["-h"], ["--help"]):
        print(_help())
        return 0
    if not arguments:
        print(_usage(), file=sys.stderr)
        return 2
    command_name, *command_argv = arguments
    command = COMMAND_BY_NAME.get(command_name)
    if command is None:
        print(f"unknown command: {command_name}", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2
    return command.handler(command_argv)
