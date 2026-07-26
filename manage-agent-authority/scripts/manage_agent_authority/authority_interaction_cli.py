"""CLI handlers for activation plans and exact authority-mode child grants."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .authority_interaction import (
    build_activation_plan,
    materialize_activation,
    materialize_mode_child,
    publish_activation_evidence,
)


def handlers(
    *,
    emit: Callable[[Any], int],
    root: Callable[[argparse.Namespace], Path],
    binding: Callable[[str, str], dict[str, str]],
    input_object: Callable[[str], dict[str, Any]],
    operation_inputs: Callable[[argparse.Namespace, Path], tuple[dict[str, Any], dict[str, Any]]],
    skills_root: Callable[[argparse.Namespace], Path | None],
) -> dict[str, Callable[[argparse.Namespace], int]]:
    def prepare(args: argparse.Namespace) -> int:
        plan_binding, plan = build_activation_plan(root(args), mode=args.mode, prepared_at=args.at)
        return emit({"activation_plan": plan_binding, "authority_interaction_mode": plan["authority_interaction_mode"], "expires_at": plan["expires_at"]})

    def publish(args: argparse.Namespace) -> int:
        return emit(publish_activation_evidence(root(args), input_object(args.evidence)))

    def materialize(args: argparse.Namespace) -> int:
        return emit(materialize_activation(root(args), binding(args.evidence, "activation_evidence")))

    def child(args: argparse.Namespace) -> int:
        workspace = root(args)
        request, _context = operation_inputs(args, workspace)
        result = materialize_mode_child(workspace, request, evaluated_at=args.at, skills_root=skills_root(args))
        if result is None:
            raise SystemExit("authority_interaction_child_not_eligible")
        return emit(result)

    return {
        "prepare_authority_interaction_activation": prepare,
        "publish_authority_interaction_evidence": publish,
        "materialize_authority_interaction_activation": materialize,
        "materialize_authority_interaction_child": child,
    }
