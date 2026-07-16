from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .audit import audit
from .contracts import (
    DEFAULT_THRESHOLDS,
    load_json,
    load_optional_contract,
    normalize_convention_contract,
)
from .source import collect_changed_files, git_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only generated-code size and module-boundary audit."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument(
        "--input-json",
        help="Governance or changed-surface JSON containing changed_files.",
    )
    parser.add_argument(
        "--convention-json",
        help="Optional JSON object or path containing code_convention_contract.",
    )
    parser.add_argument(
        "--from-git",
        action="store_true",
        help="Include git status --short changed files.",
    )
    parser.add_argument("--task-id")
    for key, value in DEFAULT_THRESHOLDS.items():
        parser.add_argument(f"--{key.replace('_', '-')}", type=int, default=value)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    files = list(args.file)
    input_data: Any = None
    if args.input_json:
        input_data = load_json(args.input_json)
        files.extend(collect_changed_files(input_data))
    if args.from_git or not files:
        files.extend(git_files(root))
    thresholds = {key: int(getattr(args, key)) for key in DEFAULT_THRESHOLDS}
    convention_contract = load_optional_contract(args.convention_json)
    if convention_contract.get("status") != "provided" and input_data is not None:
        convention_contract = normalize_convention_contract(input_data)
    result = audit(root, files, thresholds, args.task_id, convention_contract)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0
