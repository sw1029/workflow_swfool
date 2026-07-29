"""CLI handlers for read-only inspection and workflow advancement."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .workflow_status import advance_operation
from .workflow_status import inspect_operation
from .workflow_status import resolve_operation
from .workflow_status import status_snapshot


def handlers(
    *,
    emit: Callable[[Any], int],
    root: Callable[[argparse.Namespace], Path],
    operation_inputs: Callable[
        [argparse.Namespace, Path],
        tuple[dict[str, Any], dict[str, Any]],
    ],
    skills_root: Callable[[argparse.Namespace], Path | None],
) -> dict[str, Callable[[argparse.Namespace], int]]:
    def status(args: argparse.Namespace) -> int:
        return emit(
            status_snapshot(
                root(args),
                grant_id=args.grant_id,
                request_sha256=getattr(args, "request_sha256", None),
                evaluated_at=args.at,
                skills_root=skills_root(args),
            )
        )

    def run_operation(
        args: argparse.Namespace,
        operation: Callable[..., dict[str, Any]],
    ) -> int:
        workspace = root(args)
        request, context = operation_inputs(args, workspace)
        return emit(
            operation(
                workspace,
                request,
                context,
                evaluated_at=args.at,
                skills_root=skills_root(args),
            )
        )

    return {
        "status": status,
        "inspect": lambda args: run_operation(args, inspect_operation),
        "advance": lambda args: run_operation(args, advance_operation),
        "resolve": lambda args: run_operation(args, resolve_operation),
    }
