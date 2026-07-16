"""Static module command registry for validation-set operations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable, Sequence


Handler = Callable[[list[str] | None], int]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    handler: Handler
    help: str


def _build(argv: list[str] | None) -> int:
    from .build_validation_set import main

    return main(argv)


def _run_oracles(argv: list[str] | None) -> int:
    from .run_validation_oracles import main

    return main(argv)


def _leakage(argv: list[str] | None) -> int:
    from .leakage_check import main

    return main(argv)


def _finalize(argv: list[str] | None) -> int:
    from .finalize_validation_set import main

    return main(argv)


def _validate(argv: list[str] | None) -> int:
    from .validate_validation_set import main

    return main(argv)


def _freeze(argv: list[str] | None) -> int:
    from .freeze_validation_set_root import main

    return main(argv)


def _verify_root(argv: list[str] | None) -> int:
    from .verify_validation_set_root import main

    return main(argv)


COMMANDS = (
    CommandSpec("build", _build, "Create a candidate validation set."),
    CommandSpec("run-oracles", _run_oracles, "Execute deterministic oracles."),
    CommandSpec("leakage", _leakage, "Check validation-set leakage."),
    CommandSpec("finalize", _finalize, "Promote a validated candidate."),
    CommandSpec("validate", _validate, "Validate a validation set."),
    CommandSpec("freeze", _freeze, "Freeze a validation-set root."),
    CommandSpec("verify-root", _verify_root, "Verify a frozen root."),
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m build_validation_set_with_agents")
    subparsers = parser.add_subparsers(dest="command", required=True)
    specs = {spec.name: spec for spec in COMMANDS}
    if len(specs) != len(COMMANDS):
        raise RuntimeError("duplicate validation-set module command")
    for spec in COMMANDS:
        subparsers.add_parser(spec.name, add_help=False, help=spec.help)
    args, remainder = parser.parse_known_args(argv)
    return specs[args.command].handler(remainder)
