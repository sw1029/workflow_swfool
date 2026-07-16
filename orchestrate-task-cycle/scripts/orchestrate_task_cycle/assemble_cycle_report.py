#!/usr/bin/env python3
"""Stable facade for cycle-report composition."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .report.builder import ReportBuilder, ReportInputs
from .report.completion import (
    completion_evidence_findings,
    next_task_line,
    report_closure_records,
    report_closure_steps,
    report_input_findings,
    task_line,
)
from .report.constants import FIELD_ORDER, STAGE_ORDER
from .report.events import (
    all_events,
    cycle_events,
    event_value,
    long_run_events,
    long_run_status_lines,
    stage_events,
)
from .report.evidence import (
    advice_docs,
    blockers,
    changed_files,
    command_result_passed,
    command_results,
    goal_truth,
    is_resolved_blocker,
    model_effort_routing_lines,
    progress_axes,
    progress_verdict,
    report_evidence_paths,
    validation_verdict,
)
from .report.finalization import (
    finalization_consumption,
    finalization_projection,
    finalization_source,
)
from .report.io import deep_get, list_value, load_json
from .report.rendering import render_markdown


__all__ = [
    "FIELD_ORDER",
    "STAGE_ORDER",
    "advice_docs",
    "all_events",
    "assemble",
    "blockers",
    "changed_files",
    "command_result_passed",
    "command_results",
    "completion_evidence_findings",
    "cycle_events",
    "deep_get",
    "event_value",
    "finalization_consumption",
    "finalization_projection",
    "finalization_source",
    "goal_truth",
    "is_resolved_blocker",
    "list_value",
    "load_json",
    "long_run_events",
    "long_run_status_lines",
    "main",
    "model_effort_routing_lines",
    "next_task_line",
    "progress_axes",
    "progress_verdict",
    "render_markdown",
    "report_closure_records",
    "report_closure_steps",
    "report_evidence_paths",
    "report_input_findings",
    "stage_events",
    "task_line",
    "validation_verdict",
]


def assemble(
    context: dict[str, Any],
    stage: dict[str, Any],
    validation: dict[str, Any],
    progress: dict[str, Any],
    commit: dict[str, Any],
    closeout_commit: dict[str, Any],
) -> dict[str, Any]:
    return ReportBuilder().build(
        ReportInputs(
            context=context,
            stage=stage,
            validation=validation,
            progress=progress,
            commit=commit,
            closeout_commit=closeout_commit,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble a Korean orchestrate-task-cycle report draft."
    )
    parser.add_argument(
        "--context", required=True, help="Cycle context JSON path, or '-' for stdin."
    )
    parser.add_argument("--stage", help="Optional stage/status JSON path.")
    parser.add_argument("--validation", help="Optional validation result JSON path.")
    parser.add_argument("--progress", help="Optional progress-loop JSON path.")
    parser.add_argument("--commit", help="Optional commit result JSON path.")
    parser.add_argument(
        "--closeout-commit", help="Optional closeout commit result JSON path."
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    context = load_json(args.context)
    report = assemble(
        context,
        load_json(args.stage),
        load_json(args.validation),
        load_json(args.progress),
        load_json(args.commit),
        load_json(args.closeout_commit),
    )
    if args.format == "json":
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
