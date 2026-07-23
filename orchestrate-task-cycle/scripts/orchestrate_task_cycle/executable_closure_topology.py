"""Selected-successor owner adapter for executable-closure preflight."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from .executable_closure import _preflight_loaded_closure
from .selection_decision_store import normalize_binding


@contextmanager
def selected_successor_reservation_scope(
    root: Path,
    *,
    bundle_binding: dict[str, str],
    compilation_bindings: Iterable[dict[str, str]],
    decision_bindings: Iterable[dict[str, str]],
    decision_values: Iterable[dict[str, Any]] = (),
    skills_root: Path | None = None,
) -> Iterator[dict[str, Any]]:
    """Hold the owner lock order across one exact closure and its reservations."""

    workspace = root.expanduser().resolve(strict=True)
    from manage_agent_authority.canonical import authority_lock
    from manage_task_state_index.state.storage import existing_index_read_lock

    with authority_lock(workspace):
        with existing_index_read_lock(workspace) as locked:
            if not locked:
                raise ValueError(
                    "Selected-successor executable closure lacks a task-index lock"
                )
            closure = preflight_selected_successor_closure(
                workspace,
                bundle_binding=bundle_binding,
                compilation_bindings=compilation_bindings,
                decision_bindings=decision_bindings,
                decision_values=decision_values,
                skills_root=skills_root,
            )
            if (
                closure.get("status") != "ready"
                or closure.get("route") != "selected_successor_topology"
            ):
                raise ValueError(
                    "Selected-successor executable closure is not ready before reservation"
                )
            yield closure


def preflight_selected_successor_closure(
    root: Path,
    *,
    bundle_binding: dict[str, str],
    compilation_bindings: Iterable[dict[str, str]],
    decision_bindings: Iterable[dict[str, str]],
    decision_values: Iterable[dict[str, Any]] = (),
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Reopen the owner's exact topology batch before its first reservation."""

    from manage_agent_authority.operation_publication import (
        load_published_compilation,
    )

    workspace = root.expanduser().resolve(strict=True)
    normalized_bundle = normalize_binding(
        bundle_binding, "selected-successor executable-closure bundle"
    )
    from manage_agent_authority.evaluator import evaluate

    current_decisions: list[dict[str, Any]] = []
    for value in decision_values:
        if not isinstance(value, dict):
            raise ValueError("Ephemeral topology decision must be an object")
        current = evaluate(
            workspace,
            value["request"],
            value["evaluation_context"],
            evaluated_at=value["evaluated_at"],
            skills_root=skills_root,
        )
        if current != value:
            raise ValueError("Ephemeral topology decision is not a current evaluation")
        current_decisions.append(current)
    compilations: list[dict[str, Any]] = []
    normalized_compilations: list[dict[str, str]] = []
    for raw in compilation_bindings:
        binding, compilation = load_published_compilation(workspace, raw)
        normalized_compilations.append(
            {"ref": binding["ref"], "sha256": binding["sha256"]}
        )
        compilations.append(compilation)
    return _preflight_loaded_closure(
        workspace,
        compilations,
        operation_batch={
            "applicability": "selected_successor_owner_bundle",
            "bundle": normalized_bundle,
            "compilations": normalized_compilations,
        },
        operation_count=len(compilations),
        selected_successor_bundle_binding=normalized_bundle,
        decision_bindings=decision_bindings,
        decision_values=current_decisions,
    )


__all__ = (
    "preflight_selected_successor_closure",
    "selected_successor_reservation_scope",
)
