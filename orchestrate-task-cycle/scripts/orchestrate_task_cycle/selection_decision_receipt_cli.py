"""Render or validate one persisted selection-decision receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .selection_decision_receipt import (
    read_bound_json,
    read_selection_decision_receipt,
    render_preliminary_selection_decision,
    render_selection_decision_receipt,
)
from .selection_synthesis import render_selection_synthesis


def _binding(ref: str, digest: str) -> dict[str, str]:
    return {"ref": ref, "sha256": digest}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    commands = parser.add_subparsers(dest="action", required=True)
    synthesis = commands.add_parser("render-synthesis")
    synthesis.add_argument("--source-result-ref", required=True)
    synthesis.add_argument("--source-result-sha256", required=True)
    decision = commands.add_parser("render-decision")
    decision.add_argument("--trigger-tick-ref", required=True)
    decision.add_argument("--trigger-tick-sha256", required=True)
    decision.add_argument("--selection-synthesis-ref", required=True)
    decision.add_argument("--selection-synthesis-sha256", required=True)
    render = commands.add_parser("render")
    render.add_argument("--trigger-tick-ref", required=True)
    render.add_argument("--trigger-tick-sha256", required=True)
    render.add_argument("--selection-decision-ref", required=True)
    render.add_argument("--selection-decision-sha256", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--receipt-ref", required=True)
    validate.add_argument("--receipt-sha256", required=True)
    validate.add_argument("--trigger-tick-ref", required=True)
    validate.add_argument("--trigger-tick-sha256", required=True)
    return parser


def _trigger(
    root: Path, args: argparse.Namespace
) -> tuple[dict[str, str], dict[str, Any]]:
    binding = _binding(args.trigger_tick_ref, args.trigger_tick_sha256)
    _, trigger = read_bound_json(
        root,
        binding,
        "selection trigger tick",
    )
    return binding, trigger


def _run(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "render-synthesis":
        _, source_result = read_bound_json(
            root,
            _binding(args.source_result_ref, args.source_result_sha256),
            "derive synthesis source result",
        )
        return render_selection_synthesis(root, source_result)
    trigger_binding, trigger = _trigger(root, args)
    if args.action == "render-decision":
        return render_preliminary_selection_decision(
            root,
            trigger,
            _binding(
                args.selection_synthesis_ref,
                args.selection_synthesis_sha256,
            ),
        )
    if args.action == "render":
        return render_selection_decision_receipt(
            root,
            trigger,
            trigger_binding,
            _binding(
                args.selection_decision_ref,
                args.selection_decision_sha256,
            ),
        )
    return read_selection_decision_receipt(
        root,
        _binding(args.receipt_ref, args.receipt_sha256),
        expected_trigger_tick=trigger,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(Path(args.root), args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "block", "error": str(exc), "mutation_performed": False}
        code = 2
    else:
        code = 0
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
