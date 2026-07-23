"""Static module command dispatcher for the orchestration skill."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Protocol, Sequence


class CommandHandler(Protocol):
    def __call__(self, argv: Sequence[str]) -> int: ...


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    help: str
    handler: CommandHandler


def _ledger(argv: Sequence[str]) -> int:
    from .cycle_ledger import main

    return main(list(argv))


def _transition(argv: Sequence[str]) -> int:
    from .validate_cycle_transition import main

    return main(list(argv))


def _packet(argv: Sequence[str]) -> int:
    from .render_subskill_packet import main

    return main(list(argv))


def _context(argv: Sequence[str]) -> int:
    from .collect_cycle_context import main

    return main(list(argv))


def _report(argv: Sequence[str]) -> int:
    from .assemble_cycle_report import main

    return main(list(argv))


def _dashboard(argv: Sequence[str]) -> int:
    from .render_cycle_dashboard import main

    return main(list(argv))


def _result_contract(argv: Sequence[str]) -> int:
    from .result_contract.api import main

    return main(list(argv))


def _task_pack(argv: Sequence[str]) -> int:
    from .task_pack.cli import main

    return main(list(argv))


def _progress_loop(argv: Sequence[str]) -> int:
    from .progress.cli import main

    return main(list(argv))


def _gt_conflict(argv: Sequence[str]) -> int:
    from .detect_gt_constraint_conflict import main

    return main(list(argv))


def _evidence_cache(argv: Sequence[str]) -> int:
    from .evidence_cache import main

    return main(list(argv))


def _mode_profile(argv: Sequence[str]) -> int:
    from .mode_profile import main

    return main(list(argv))


def _model_effort(argv: Sequence[str]) -> int:
    from .model_effort_router import main

    return main(list(argv))


def _monitor(argv: Sequence[str]) -> int:
    from .monitor_running_execution import main

    return main(list(argv))


def _output_delta(argv: Sequence[str]) -> int:
    from .output_delta_contract import main

    return main(list(argv))


def _efficiency(argv: Sequence[str]) -> int:
    from .profile_cycle_efficiency import main

    return main(list(argv))


def _visible_increment(argv: Sequence[str]) -> int:
    from .visible_increment import main

    return main(list(argv))


def _code_structure(argv: Sequence[str]) -> int:
    from .code_structure_audit import main

    return main(list(argv))


def _changed_surface(argv: Sequence[str]) -> int:
    from .changed_surface import main

    return main(list(argv))


def _validation_scope(argv: Sequence[str]) -> int:
    from .validation_scope import main

    return main(list(argv))


def _selection_tick(argv: Sequence[str]) -> int:
    from .selection_tick import main

    return main(list(argv))


def _selection_decision_receipt(argv: Sequence[str]) -> int:
    from .selection_decision_receipt_cli import main

    return main(list(argv))


def _authority_reentry(argv: Sequence[str]) -> int:
    from .selection_authority_reentry_cli import main

    return main(list(argv))


def _selection_publication(argv: Sequence[str]) -> int:
    from .selection_publication_cli import main

    return main(list(argv))


def _selected_successor(argv: Sequence[str]) -> int:
    from .selected_successor_cli import main

    return main(list(argv))


def _executable_closure(argv: Sequence[str]) -> int:
    from .executable_closure import main

    return main(list(argv))


def _terminal_wait_baseline(argv: Sequence[str]) -> int:
    from .terminal_wait_baseline_cli import main

    return main(list(argv))


def _exact_subject_premise(argv: Sequence[str]) -> int:
    from .exact_subject_premise_cli import main

    return main(list(argv))


def _repo_adapter(argv: Sequence[str]) -> int:
    from .repo_skill_adapter import main

    return main(list(argv))


def _authority_packet(argv: Sequence[str]) -> int:
    from .authority_packet import main

    return main(list(argv))


def _stage(argv: Sequence[str]) -> int:
    from .stage.cli import main

    return main(list(argv))


def _workflow(argv: Sequence[str]) -> int:
    from .workflow_launcher import main

    return main(list(argv))


COMMANDS = (
    CommandSpec("ledger", "manage the durable cycle ledger", _ledger),
    CommandSpec("transition", "validate cycle stage transitions", _transition),
    CommandSpec("packet", "render a subskill packet", _packet),
    CommandSpec("context", "collect cycle context", _context),
    CommandSpec("report", "assemble the final cycle report", _report),
    CommandSpec("dashboard", "render the cycle dashboard", _dashboard),
    CommandSpec("result-contract", "validate a subskill result", _result_contract),
    CommandSpec("task-pack", "manage task-pack state", _task_pack),
    CommandSpec("progress-loop", "detect repeated progress loops", _progress_loop),
    CommandSpec("gt-conflict", "detect goal-truth conflicts", _gt_conflict),
    CommandSpec("evidence-cache", "manage reusable evidence", _evidence_cache),
    CommandSpec("mode-profile", "validate and resolve workflow modes", _mode_profile),
    CommandSpec("model-effort", "resolve model and effort routing", _model_effort),
    CommandSpec("monitor", "inspect a long-running execution", _monitor),
    CommandSpec("output-delta", "validate output-delta evidence", _output_delta),
    CommandSpec("efficiency", "profile cycle efficiency", _efficiency),
    CommandSpec("visible-increment", "record a visible increment", _visible_increment),
    CommandSpec("code-structure", "audit code structure", _code_structure),
    CommandSpec(
        "changed-surface",
        "classify the orchestration changed surface",
        _changed_surface,
    ),
    CommandSpec(
        "validation-scope",
        "select the orchestration validation scope",
        _validation_scope,
    ),
    CommandSpec(
        "selection-tick",
        "compare terminal-wait selection inputs without starting a cycle",
        _selection_tick,
    ),
    CommandSpec(
        "selection-decision-receipt",
        "render or validate one persisted selection acknowledgement",
        _selection_decision_receipt,
    ),
    CommandSpec(
        "authority-reentry",
        "compile a settled user-escalation authority delta",
        _authority_reentry,
    ),
    CommandSpec(
        "selection-publication",
        "publish one selected task with forward recovery",
        _selection_publication,
    ),
    CommandSpec(
        "selected-successor",
        "prepare one body-free selected-successor lifecycle",
        _selected_successor,
    ),
    CommandSpec(
        "executable-closure",
        "verify that an exact operation batch may execute now",
        _executable_closure,
    ),
    CommandSpec(
        "terminal-wait-baseline",
        "publish and resolve an authority-settled selection baseline",
        _terminal_wait_baseline,
    ),
    CommandSpec(
        "exact-subject-premise",
        "validate a premise against locally bound evidence artifacts",
        _exact_subject_premise,
    ),
    CommandSpec(
        "repo-adapter",
        "scan and hand off repository-owned workflow adapters",
        _repo_adapter,
    ),
    CommandSpec(
        "authority-packet",
        "construct and verify an authority owner projection",
        _authority_packet,
    ),
    CommandSpec(
        "stage",
        "prepare, submit, or boundedly advance a compiled stage",
        _stage,
    ),
    CommandSpec(
        "workflow",
        "run a workflow owner with exact sibling dependencies",
        _workflow,
    ),
)
COMMANDS_BY_NAME = {spec.name: spec for spec in COMMANDS}
if len(COMMANDS_BY_NAME) != len(COMMANDS):
    raise RuntimeError("duplicate orchestrate-task-cycle command")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m orchestrate_task_cycle")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    for spec in COMMANDS:
        commands.add_parser(spec.name, help=spec.help, add_help=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    if not arguments or arguments[0] in {"-h", "--help"}:
        parser.print_help()
        return 0
    spec = COMMANDS_BY_NAME.get(arguments[0])
    if spec is None:
        parser.error(f"invalid command: {arguments[0]}")
    return spec.handler(arguments[1:])


__all__ = ["COMMANDS", "CommandHandler", "CommandSpec", "main"]
