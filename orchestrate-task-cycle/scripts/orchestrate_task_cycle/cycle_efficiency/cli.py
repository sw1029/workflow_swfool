from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis import analyze
from .common import collect_events, read_jsonl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Profile task-cycle efficiency from ledger/index evidence."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--cycle-id")
    parser.add_argument(
        "--task-id",
        required=True,
        help="Canonical task ID for the formal cycle_efficiency_profile envelope.",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    output = analyze(
        root,
        collect_events(root, args.cycle_id),
        read_jsonl(root / ".task" / "index.jsonl"),
        args.task_id,
    )
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0
