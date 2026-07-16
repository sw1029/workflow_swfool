#!/usr/bin/env python3
"""Stable facade for the typed subskill-packet builder pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import model_effort_router
from .packet.builder import PacketBuilder
from .packet.context import (
    PacketBuildContext,
    active_advice,
    authority_policy,
    available_goal_truth,
    counts,
    deep_get,
    enrich_advice,
    goal_truth,
    load_json,
    output_delta_contract_packet as _output_delta_contract_packet,
    parse_advice_document,
    routing_request_for,
    section_bullets,
    section_lines,
    section_text,
    task_summary,
)
from .packet.registry import TARGET_BUILDERS
from .packet.rendering import render_markdown


TARGETS = set(TARGET_BUILDERS)
OUTPUT_DELTA_CONTRACT_CANDIDATES = (
    ".task/contracts/output_delta_contract.json",
    ".agent_goal/output_delta_contract.json",
)
MODEL_EFFORT_PROFILE_PATH = (
    Path(__file__).resolve().parents[2] / "references" / "model-effort-profiles.json"
)
ROUTING_REFERENCE_PATH = (
    Path(__file__).resolve().parents[2] / "references" / "workflow-routing.md"
)

MODEL_EFFORT_ROUTER = model_effort_router
MODEL_EFFORT_POLICY = MODEL_EFFORT_ROUTER.load_policy(MODEL_EFFORT_PROFILE_PATH)

__all__ = [
    "MODEL_EFFORT_POLICY",
    "MODEL_EFFORT_PROFILE_PATH",
    "MODEL_EFFORT_ROUTER",
    "OUTPUT_DELTA_CONTRACT_CANDIDATES",
    "ROUTING_REFERENCE_PATH",
    "TARGETS",
    "active_advice",
    "authority_policy",
    "available_goal_truth",
    "counts",
    "deep_get",
    "enrich_advice",
    "goal_truth",
    "load_json",
    "main",
    "output_delta_contract_packet",
    "packet_for",
    "parse_advice_document",
    "render_markdown",
    "routing_profile",
    "routing_request_for",
    "section_bullets",
    "section_lines",
    "section_text",
    "task_summary",
]


def routing_profile(
    profile_id: str, request: dict[str, Any] | None = None
) -> dict[str, Any]:
    return MODEL_EFFORT_ROUTER.select_route(profile_id, request, MODEL_EFFORT_POLICY)


def output_delta_contract_packet(context: dict[str, Any]) -> dict[str, Any] | None:
    return _output_delta_contract_packet(context, OUTPUT_DELTA_CONTRACT_CANDIDATES)


def packet_for(
    target: str,
    context: dict[str, Any],
    stage: dict[str, Any],
    workflow_mode: str = "normal",
) -> dict[str, Any]:
    build_context = PacketBuildContext(
        context=context,
        stage=stage,
        model_effort_policy=MODEL_EFFORT_POLICY,
        model_effort_profile_path=MODEL_EFFORT_PROFILE_PATH,
        routing_reference_path=ROUTING_REFERENCE_PATH,
        route_selector=routing_profile,
        output_delta_contract_candidates=OUTPUT_DELTA_CONTRACT_CANDIDATES,
    )
    return PacketBuilder().build(target, build_context, workflow_mode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a routing packet for an orchestrate-task-cycle subskill call."
    )
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--context", help="Cycle context JSON path, or '-' for stdin.")
    parser.add_argument("--stage", help="Optional stage/status JSON path.")
    parser.add_argument(
        "--workflow-mode", choices=("normal", "bootstrap"), default="normal"
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    context = load_json(args.context)
    stage = load_json(args.stage)
    packet = packet_for(args.target, context, stage, args.workflow_mode)
    if args.format == "json":
        json.dump(packet, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
