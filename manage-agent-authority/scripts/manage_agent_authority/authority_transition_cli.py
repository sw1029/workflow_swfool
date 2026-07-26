"""Small isolated handler for governed grant-state transitions."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .artifact_store import transition_grants


def command_transition(
    args: argparse.Namespace,
    *,
    emit: Callable[[Any], int] | None = None,
    root: Callable[[argparse.Namespace], Path] | None = None,
    binding: Callable[[str, str], dict[str, str]] | None = None,
) -> int:
    if emit is None or root is None or binding is None:
        from .authority_cli import _binding, _emit, _root

        emit, root, binding = _emit, _root, _binding
    result = transition_grants(
        root(args), args.grant_id, args.transition, event_id=args.event_id,
        expected_version=args.expected_version,
        source_approval=binding(args.source_approval, "source_approval"),
        transitioned_at=args.at,
    )
    return emit({"status": args.transition, **result})
