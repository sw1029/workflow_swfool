from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis import analyze
from .constant_registry import validate_constant_registry
from .constants import REGISTRY_REL_PATH

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect repeated safety-only/no-live progress loops before task derivation.")
    parser.add_argument("--root", default=".", help="Workspace root to inspect.")
    parser.add_argument("--recent", type=int, help="Explicit evidence-scope limit; omitted scope is not_evaluated unless policy supplies evidence_scope_limit.")
    parser.add_argument("--strict", action="store_true", help="Return block when consecutive safety_only evidence repeats the same blocker.")
    parser.add_argument("--goal-productive-threshold", type=int, help="Activate the goal-productive staleness budget at this explicit value.")
    parser.add_argument("--root-axis-threshold", type=int, help="Activate the same-axis nonsemantic replay budget at this explicit value.")
    parser.add_argument("--feature-symbol-threshold", type=int, help="Activate the same-feature no-material-delta budget at this explicit value.")
    parser.add_argument("--terminal-quiescence-threshold", type=int, help="Activate terminal quiescence at this explicit streak value.")
    parser.add_argument("--terminal-escalation-threshold", type=int, help="Activate terminal escalation at this explicit streak value.")
    parser.add_argument(
        "--policy-json",
        help="Optional repository-adapter policy packet as a JSON object.",
    )
    parser.add_argument(
        "--finalized-cycle-id",
        help="Optional cycle ID whose current finalization receipt must verify before registry consumption.",
    )
    parser.add_argument(
        "--write-registry",
        action="store_true",
        help=(
            "Compatibility flag: prepare a typed replacement projection for "
            f"{REGISTRY_REL_PATH}; publication requires cycle finalization."
        ),
    )
    parser.add_argument("--verify-constant-registry", action="store_true", help="Validate progress_loop_detection/constant_registry.json against runtime constants.")
    args = parser.parse_args(argv)

    if args.verify_constant_registry:
        result = validate_constant_registry()
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if result["status"] != "block" else 2

    numeric_args = (
        "recent",
        "goal_productive_threshold",
        "root_axis_threshold",
        "feature_symbol_threshold",
        "terminal_quiescence_threshold",
        "terminal_escalation_threshold",
    )
    for name in numeric_args:
        value = getattr(args, name)
        if value is not None and value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be greater than zero")
    policy = None
    if args.policy_json is not None:
        try:
            policy = json.loads(args.policy_json)
        except json.JSONDecodeError as exc:
            parser.error(f"--policy-json is not valid JSON: {exc.msg}")

    result = analyze(
        Path(args.root).resolve(),
        args.recent,
        args.strict,
        args.goal_productive_threshold,
        args.root_axis_threshold,
        args.feature_symbol_threshold,
        args.terminal_quiescence_threshold,
        args.terminal_escalation_threshold,
        args.write_registry,
        policy,
        args.finalized_cycle_id,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] != "block" else 2
