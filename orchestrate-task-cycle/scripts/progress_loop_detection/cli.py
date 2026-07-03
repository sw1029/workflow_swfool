from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis import analyze
from .constant_registry import validate_constant_registry
from .constants import REGISTRY_REL_PATH, TERMINAL_ESCALATION_STREAK_DEFAULT, TERMINAL_QUIESCENCE_STREAK_DEFAULT

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect repeated safety-only/no-live progress loops before task derivation.")
    parser.add_argument("--root", default=".", help="Workspace root to inspect.")
    parser.add_argument("--recent", type=int, default=8, help="Number of recent evidence files to inspect.")
    parser.add_argument("--strict", action="store_true", help="Return block when consecutive safety_only evidence repeats the same blocker.")
    parser.add_argument("--goal-productive-threshold", type=int, default=5, help="Warn/block when this many recent progress cycles lack goal-productive output.")
    parser.add_argument("--root-axis-threshold", type=int, default=6, help="Hard-stop after this many same-root-axis governance-only/provider-neutral records without domain delta.")
    parser.add_argument("--feature-symbol-threshold", type=int, default=6, help="Hard-stop after this many same-feature-symbol records without observed node/edge delta.")
    parser.add_argument("--terminal-quiescence-threshold", type=int, default=TERMINAL_QUIESCENCE_STREAK_DEFAULT, help="Stop automatic domain-cycle restart after this many same-root terminal records without input delta.")
    parser.add_argument("--terminal-escalation-threshold", type=int, default=TERMINAL_ESCALATION_STREAK_DEFAULT, help="Escalate repeated terminal_blocked/recheck records for the same root family to user_escalation after this many records without input delta.")
    parser.add_argument("--write-registry", action="store_true", help=f"Append the newest progress feature symbol to {REGISTRY_REL_PATH}.")
    parser.add_argument("--verify-constant-registry", action="store_true", help="Validate progress_loop_detection/constant_registry.json against runtime constants.")
    args = parser.parse_args(argv)

    if args.verify_constant_registry:
        result = validate_constant_registry()
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if result["status"] != "block" else 2

    result = analyze(
        Path(args.root).resolve(),
        max(1, args.recent),
        args.strict,
        max(1, args.goal_productive_threshold),
        max(1, args.root_axis_threshold),
        max(1, args.feature_symbol_threshold),
        max(1, args.terminal_quiescence_threshold),
        max(1, args.terminal_escalation_threshold),
        args.write_registry,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] != "block" else 2
