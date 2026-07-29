"""Synchronize the generated workflow surface in the root README."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .cli import COMMANDS
from .ledger.constants import CANONICAL_STEP_ORDER


README_PATH = Path(__file__).resolve().parents[3] / "README.md"
COMMAND_TABLE_START = "<!-- workflow-docs:command-table:start -->"
COMMAND_TABLE_END = "<!-- workflow-docs:command-table:end -->"
PHASE_FLOW_START = "<!-- workflow-docs:phase-flow:start -->"
PHASE_FLOW_END = "<!-- workflow-docs:phase-flow:end -->"


def _replace_region(text: str, start: str, end: str, body: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"README requires one generated region: {start}")
    before, remainder = text.split(start, 1)
    _old, after = remainder.split(end, 1)
    return f"{before}{start}\n{body.rstrip()}\n{end}{after}"


def _replace_command_row(text: str) -> str:
    if text.count(COMMAND_TABLE_START) != 1 or text.count(COMMAND_TABLE_END) != 1:
        raise ValueError("README requires one generated command-table region")
    before, remainder = text.split(COMMAND_TABLE_START, 1)
    table, after = remainder.split(COMMAND_TABLE_END, 1)
    lines = table.strip("\n").splitlines()
    matches = [
        index
        for index, line in enumerate(lines)
        if line.startswith("| `orchestrate-task-cycle` |")
    ]
    if len(matches) != 1:
        raise ValueError("README command table requires one orchestrator row")
    lines[matches[0]] = command_row()
    table_body = "\n".join(lines)
    return (
        f"{before}{COMMAND_TABLE_START}\n"
        f"{table_body}\n"
        f"{COMMAND_TABLE_END}{after}"
    )


def command_row() -> str:
    names = ", ".join(f"`{spec.name}`" for spec in COMMANDS)
    return (
        "| `orchestrate-task-cycle` | `orchestrate_task_cycle` | "
        f"{len(COMMANDS)}개: {names} |"
    )


def phase_flow() -> str:
    chain = " --> ".join(CANONICAL_STEP_ORDER)
    return (
        f"### Canonical normal-cycle phase flow ({len(CANONICAL_STEP_ORDER)})\n\n"
        "아래 순서는 runtime ledger registry에서 생성된다.\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        f"  {chain}\n"
        "```"
    )


def render_readme(text: str) -> str:
    rendered = _replace_command_row(text)
    return _replace_region(
        rendered,
        PHASE_FLOW_START,
        PHASE_FLOW_END,
        phase_flow(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check or update generated root README workflow sections."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    current = README_PATH.read_text(encoding="utf-8")
    expected = render_readme(current)
    if args.check:
        if current != expected:
            print(f"generated workflow docs are stale: {README_PATH}")
            return 1
        print(f"generated workflow docs are current: {README_PATH}")
        return 0
    README_PATH.write_text(expected, encoding="utf-8")
    print(f"updated generated workflow docs: {README_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
