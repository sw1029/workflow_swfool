"""CLI for full and model-facing cycle-context projections."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .collect_cycle_context import collect
from .model_context import project_model_context


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect compact evidence for an orchestrate-task-cycle run."
    )
    parser.add_argument("--root", default=".", help="Workspace root to inspect.")
    parser.add_argument(
        "--include-git",
        action="store_true",
        help="Include Git worktree and status evidence.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=12,
        help="Maximum recent files per artifact group.",
    )
    parser.add_argument(
        "--cycle-id",
        help="Optional exact cycle to project instead of the latest cycle.",
    )
    parser.add_argument(
        "--projection",
        choices=("full", "model"),
        default="full",
        help="Preserve the legacy full context or render a compact model-facing view.",
    )
    parser.add_argument(
        "--model-max-paths",
        type=int,
        default=40,
        help="Maximum diagnostic paths retained by the model projection.",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.exists():
        parser.error(f"--root does not exist: {root}")
    context = collect(
        root,
        args.include_git,
        max(1, args.max_files),
        args.cycle_id,
    )
    if args.projection == "model":
        context = project_model_context(context, max_paths=max(1, args.model_max_paths))
    json.dump(
        context,
        sys.stdout,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
