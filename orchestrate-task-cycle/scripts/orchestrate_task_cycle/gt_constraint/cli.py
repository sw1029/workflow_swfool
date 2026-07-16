from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis import analyze
from .common import read_json_arg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect task constraints that contradict allowed or required goal-truth actions."
    )
    parser.add_argument("--root", default=".", help="Workspace root.")
    parser.add_argument(
        "--task",
        default="task.md",
        help="Task Markdown path, relative to --root unless absolute.",
    )
    parser.add_argument(
        "--behavior-json", help="JSON object or path with safe scalar run behavior."
    )
    parser.add_argument(
        "--behavior-path", help="Path to JSON with safe scalar run behavior."
    )
    parser.add_argument(
        "--policy-json",
        help="Explicit repository-adapter GT constraint policy JSON object or path.",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    task_path = Path(args.task)
    if not task_path.is_absolute():
        task_path = root / task_path
    behavior = read_json_arg(root, args.behavior_json) or read_json_arg(
        root, args.behavior_path
    )
    policy = read_json_arg(root, args.policy_json)
    result = analyze(root, task_path, behavior, policy)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] != "block" else 2
