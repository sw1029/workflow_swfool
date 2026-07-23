"""Producer-specific ledger publication without caller-selected producer labels."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .compiler_binding import (
    CompiledEventBinding,
    compile_stage_observation,
    compile_system_event,
    compile_terminal_lifecycle,
    open_compiled_event_binding,
)
from .constants import COMPILED_STAGE_RESULT_EVENT_KIND
from .repository import append_compiled_binding, read_current_expanded, read_events
from .result_hydration import validate_compact_result_envelope
from .semantic_seeds import StageObservationSeed, TerminalLifecycleSeed
from .support import (
    current_stage_path,
    ledger_path,
    read_initialization_metadata,
    rel_path,
)


def _publish(
    root: Path,
    cycle_id: str,
    binding: CompiledEventBinding,
) -> dict[str, Any]:
    return append_compiled_binding(root, cycle_id, binding)


def append_compiled_system_stage(
    root: Path,
    cycle_id: str,
    step: str,
    *,
    max_files: int = 12,
    max_paths: int = 40,
) -> dict[str, Any]:
    """Re-derive a canonical system event from exact workspace/cycle state."""

    from ..stage.specs import TARGET_COMPILE_SPECS
    from ..stage.system_steps import render_context_event, render_system_event
    from ..stage.v2_context import collect_selected_context

    metadata = read_initialization_metadata(root, cycle_id)
    task_id = metadata.get("task_id")
    if step == "context":
        previous = read_events(root, cycle_id)
        if previous:
            if previous[0].get("step") != "context":
                raise ValueError(
                    "cycle ledger is invalid: first canonical stage is not context"
                )
            return {
                "event": previous[0],
                "event_duplicate": True,
                "current_stage": read_current_expanded(root, cycle_id),
                "ledger_path": rel_path(root, ledger_path(root, cycle_id)),
                "current_stage_path": rel_path(
                    root, current_stage_path(root, cycle_id)
                ),
            }
        full, model, _metrics = collect_selected_context(
            root,
            cycle_id,
            TARGET_COMPILE_SPECS["authority"],
            max_files=max_files,
            max_paths=max_paths,
        )
        event = render_context_event(cycle_id, task_id, full, model)
    else:
        event = render_system_event(
            cycle_id, step, task_id, read_events(root, cycle_id)
        )
    return _publish(root, cycle_id, compile_system_event(event))


def append_compiled_stage_result_binding(
    root: Path, cycle_id: str, binding: CompiledEventBinding
) -> dict[str, Any]:
    """Publish only an opaque result binding derived from exact compiler inputs."""

    compiled, producer = open_compiled_event_binding(binding)
    if (
        producer != "stage_result_compiler"
        or compiled.get("event_kind") != COMPILED_STAGE_RESULT_EVENT_KIND
    ):
        raise ValueError("compiled stage result publication received another producer")
    validate_compact_result_envelope(compiled, cycle_id)
    return _publish(root, cycle_id, binding)


def append_compiled_stage_observation(
    root: Path, cycle_id: str, seed: StageObservationSeed
) -> dict[str, Any]:
    return _publish(root, cycle_id, compile_stage_observation(seed))


def append_compiled_terminal_lifecycle(
    root: Path, cycle_id: str, seed: TerminalLifecycleSeed
) -> dict[str, Any]:
    return _publish(root, cycle_id, compile_terminal_lifecycle(seed))


__all__ = [
    "append_compiled_stage_observation",
    "append_compiled_stage_result_binding",
    "append_compiled_system_stage",
    "append_compiled_terminal_lifecycle",
]
