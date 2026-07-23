#!/usr/bin/env python3
"""Stable facade for the fail-closed cycle-dashboard pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .dashboard.builder import DashboardBuilder, DashboardInputs
from .dashboard.collections import (
    collect_fields,
    event_malformed_reasons,
    evidence_paths,
    latest_value,
    long_run_events,
    unique,
    values,
)
from .dashboard.constants import (
    AXIS_FIELDS,
    CANONICAL_STEPS,
    CYCLE_ID_PATTERN,
    DEFAULT_STEPS,
    PART_L_M_FIELDS,
    VERDICT_AXIS_FIELDS,
)
from .dashboard.errors import DashboardDataError
from .dashboard.io import atomic_write, load_current, load_events
from .dashboard.rendering import render_summary
from .ledger.support import read_initialization_metadata
from .ledger.workflow_contract import require_cycle_mutation_contract


__all__ = [
    "AXIS_FIELDS",
    "CANONICAL_STEPS",
    "CYCLE_ID_PATTERN",
    "DEFAULT_STEPS",
    "DashboardDataError",
    "PART_L_M_FIELDS",
    "VERDICT_AXIS_FIELDS",
    "atomic_write",
    "collect_fields",
    "event_malformed_reasons",
    "evidence_paths",
    "latest_value",
    "load_current",
    "load_events",
    "long_run_events",
    "main",
    "render",
    "render_summary",
    "summarize",
    "unique",
    "values",
]


def summarize(
    events: list[dict[str, Any]],
    current: dict[str, Any],
    current_load_status: str,
    cycle_id: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    return DashboardBuilder().build(
        DashboardInputs(
            events=events,
            current=current,
            current_load_status=current_load_status,
            cycle_id=cycle_id,
            workspace_root=workspace_root,
        )
    )


def render(
    events: list[dict[str, Any]],
    cycle_id: str,
    current: dict[str, Any] | None = None,
    current_load_status: str = "missing",
) -> str:
    return render_summary(
        summarize(events, current or {}, current_load_status, cycle_id)
    )


def _write_error(message: str, output_format: str) -> None:
    if output_format == "json":
        json.dump(
            {
                "format_version": 1,
                "step": "dashboard",
                "dashboard_status": "block",
                "error": message,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
    else:
        sys.stderr.write(f"dashboard blocked: {message}\n")


def _safe_cycle_paths(root: Path, cycle_id: str) -> tuple[Path, Path, Path, Path]:
    cycle_directory = root / ".task" / "cycle" / cycle_id
    ledger = cycle_directory / "stage.jsonl"
    current = cycle_directory / "current_stage.json"
    dashboard = cycle_directory / "dashboard.md"
    for label, path in (
        ("cycle directory", cycle_directory),
        ("ledger", ledger),
        ("current snapshot", current),
        ("dashboard", dashboard),
    ):
        try:
            path.resolve(strict=False).relative_to(root)
        except ValueError as exc:
            raise DashboardDataError(
                f"{label} escapes the workspace root, including through a symlink"
            ) from exc
    return cycle_directory, ledger, current, dashboard


def _safe_result_path(root: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise DashboardDataError(
            "result output must stay inside workspace root"
        ) from exc
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a fail-closed .task/cycle dashboard and result contract."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--result-output", help="Optional dashboard result-contract JSON path."
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not CYCLE_ID_PATTERN.fullmatch(args.cycle_id):
        _write_error("cycle_id is not path-safe", args.format)
        return 2
    try:
        _cycle_directory, ledger, current_path, dashboard_path = _safe_cycle_paths(
            root, args.cycle_id
        )
        result_path = _safe_result_path(root, args.result_output)
        if args.write or result_path is not None:
            metadata = read_initialization_metadata(root, args.cycle_id)
            require_cycle_mutation_contract(metadata, "render cycle dashboard")
        events = load_events(ledger)
    except (DashboardDataError, ValueError) as exc:
        _write_error(str(exc), args.format)
        return 2
    current, current_load_status = load_current(current_path)
    summary = summarize(events, current, current_load_status, args.cycle_id, root)
    markdown = render_summary(summary)
    if args.write:
        atomic_write(dashboard_path, markdown)
    summary["dashboard_path"] = (
        dashboard_path.relative_to(root).as_posix()
        if args.write
        else "stdout:dashboard"
    )
    summary["evidence_paths"] = unique(
        [ledger.relative_to(root).as_posix()]
        + (
            [current_path.relative_to(root).as_posix()]
            if current_path.is_file()
            else []
        )
        + ([summary["dashboard_path"]] if args.write else [])
        + summary["artifacts"]
    )
    if result_path is not None:
        summary["result_path"] = result_path.relative_to(root).as_posix()
        summary["evidence_paths"] = unique(
            summary["evidence_paths"] + [summary["result_path"]]
        )
        atomic_write(
            result_path,
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    if args.format == "json":
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
