"""Opaque, producer-specific bindings for compiler-owned ledger events."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .constants import (
    COMPILED_STAGE_OBSERVATION_EVENT_KIND,
    COMPILED_STAGE_RESULT_EVENT_KIND,
    COMPILED_SYSTEM_EVENT_KIND,
    COMPILED_TERMINAL_LIFECYCLE_EVENT_KIND,
)
from .semantic_seeds import (
    StageObservationSeed,
    TerminalLifecycleSeed,
    open_stage_observation_seed,
    open_terminal_lifecycle_seed,
)
from .stage_result_compiler import (
    derive_stage_result_event,
    make_stage_result_derivation,
    validate_derivation_shape,
    validate_stage_result_derivation,
)
from .support import canonical_json_bytes


_COMPILER_CAPABILITY = object()
_SYSTEM_CONTEXT_FIELDS = {
    "step",
    "status",
    "event_id",
    "reason",
    "task_id",
    "task_absent",
    "task_md",
    "used_goal_truth",
    "used_advice",
    "context_fingerprint",
}
_SYSTEM_CHECKPOINT_FIELDS = {
    "step",
    "status",
    "event_id",
    "reason",
    "task_id",
    "compiler_protocol_version",
    "predecessor_event_id",
}


@dataclass(frozen=True, slots=True)
class CompiledEventBinding:
    canonical_event: bytes
    producer_kind: str
    event_kind: str
    _capability: object
    derivation_material: bytes | None = None


@dataclass(frozen=True, slots=True)
class _ProducerSpec:
    producer_kind: str
    event_kind: str


_SYSTEM = _ProducerSpec("system_event_compiler", COMPILED_SYSTEM_EVENT_KIND)
_STAGE_RESULT = _ProducerSpec(
    "stage_result_compiler", COMPILED_STAGE_RESULT_EVENT_KIND
)
_STAGE_OBSERVATION = _ProducerSpec(
    "stage_observer", COMPILED_STAGE_OBSERVATION_EVENT_KIND
)
_TERMINAL = _ProducerSpec(
    "terminal_lifecycle_compiler", COMPILED_TERMINAL_LIFECYCLE_EVENT_KIND
)


def _seal(
    event: dict[str, Any],
    spec: _ProducerSpec,
    *,
    derivation_material: bytes | None = None,
) -> CompiledEventBinding:
    if not isinstance(event, dict):
        raise ValueError("compiled ledger semantic input must be an object")
    if "event_kind" in event or "producer_kind" in event:
        raise ValueError("semantic event must not author compiler-owned labels")
    compiled = {
        **event,
        "event_kind": spec.event_kind,
        "producer_kind": spec.producer_kind,
    }
    return CompiledEventBinding(
        canonical_event=canonical_json_bytes(compiled),
        producer_kind=spec.producer_kind,
        event_kind=spec.event_kind,
        _capability=_COMPILER_CAPABILITY,
        derivation_material=derivation_material,
    )


def compile_system_event(event: dict[str, Any]) -> CompiledEventBinding:
    allowed = (
        _SYSTEM_CONTEXT_FIELDS
        if event.get("step") == "context"
        else _SYSTEM_CHECKPOINT_FIELDS
    )
    if set(event) - allowed:
        raise ValueError("system event contains non-derived fields")
    if event.get("step") == "context":
        required = {"status", "event_id", "task_id", "context_fingerprint"}
    else:
        required = {
            "step",
            "status",
            "event_id",
            "compiler_protocol_version",
            "predecessor_event_id",
        }
    if not required <= set(event):
        raise ValueError("system event is missing compiler-derived fields")
    return _seal(event, _SYSTEM)


def compile_stage_result_binding(
    preparation: dict[str, Any],
    result: dict[str, Any],
    result_ref: str,
    result_sha256: str,
    compiler_metrics: dict[str, Any] | None,
    input_bindings: dict[str, Any] | None,
    collection_limits: dict[str, Any],
    previous_events: list[dict[str, Any]],
) -> CompiledEventBinding:
    derivation = make_stage_result_derivation(
        preparation,
        result,
        result_ref,
        result_sha256,
        compiler_metrics,
        input_bindings,
        collection_limits,
        previous_events,
    )
    event = derive_stage_result_event(
        derivation["preparation"],
        derivation["result"],
        derivation["result_ref"],
        derivation["result_sha256"],
        derivation["compiler_metrics"],
        derivation["input_bindings"],
    )
    return _seal(
        event,
        _STAGE_RESULT,
        derivation_material=canonical_json_bytes(derivation),
    )


def compile_stage_observation(seed: StageObservationSeed) -> CompiledEventBinding:
    semantic = open_stage_observation_seed(seed)
    event = {
        **semantic,
        "step": "run",
        "status": "partial",
        "reason": str(
            semantic.get("reason")
            or "long-running execution observation recorded without success promotion"
        ),
    }
    return _seal(event, _STAGE_OBSERVATION)


def compile_terminal_lifecycle(seed: TerminalLifecycleSeed) -> CompiledEventBinding:
    semantic = open_terminal_lifecycle_seed(seed)
    event = {
        **semantic,
        "step": "report",
        "status": "complete",
        "reason": str(
            semantic.get("reason") or "compiled terminal lifecycle observation"
        ),
    }
    return _seal(event, _TERMINAL)


def _opened_derivation(binding: CompiledEventBinding) -> dict[str, Any]:
    if binding.derivation_material is None:
        raise ValueError("compiled stage result lacks exact derivation material")
    try:
        value = json.loads(binding.derivation_material)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("compiled stage result derivation material is malformed") from exc
    if canonical_json_bytes(value) != binding.derivation_material:
        raise ValueError("compiled stage result derivation integrity failed")
    return validate_derivation_shape(value)


def _validate_opened_event(event: dict[str, Any], binding: CompiledEventBinding) -> None:
    if (
        event.get("event_kind") != binding.event_kind
        or event.get("producer_kind") != binding.producer_kind
    ):
        raise ValueError("compiled ledger event binding integrity failed")
    if binding.producer_kind == _SYSTEM.producer_kind:
        semantic = {
            key: item
            for key, item in event.items()
            if key not in {"event_kind", "producer_kind"}
        }
        compile_system_event(semantic)
    elif binding.producer_kind == _STAGE_OBSERVATION.producer_kind:
        if event.get("step") != "run" or not event.get("observation_kind"):
            raise ValueError("compiled stage observation is invalid")
    elif binding.producer_kind == _TERMINAL.producer_kind:
        if event.get("step") != "report":
            raise ValueError("compiled terminal lifecycle event is invalid")
    elif binding.producer_kind == _STAGE_RESULT.producer_kind:
        derivation = _opened_derivation(binding)
        expected = derive_stage_result_event(
            derivation["preparation"],
            derivation["result"],
            derivation["result_ref"],
            derivation["result_sha256"],
            derivation["compiler_metrics"],
            derivation["input_bindings"],
        )
        semantic = {
            key: item
            for key, item in event.items()
            if key not in {"event_kind", "producer_kind"}
        }
        if canonical_json_bytes(semantic) != canonical_json_bytes(expected):
            raise ValueError(
                "compiled stage result differs from sealed derivation material"
            )
    else:
        raise ValueError("compiled ledger producer is not registered")


def open_compiled_event_binding(
    binding: CompiledEventBinding,
) -> tuple[dict[str, Any], str]:
    if (
        not isinstance(binding, CompiledEventBinding)
        or binding._capability is not _COMPILER_CAPABILITY
    ):
        raise ValueError(
            "typed ledger publication requires a compiler-owned event binding"
        )
    try:
        event = json.loads(binding.canonical_event)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("compiled ledger event binding is malformed") from exc
    if (
        not isinstance(event, dict)
        or canonical_json_bytes(event) != binding.canonical_event
    ):
        raise ValueError("compiled ledger event binding integrity failed")
    _validate_opened_event(event, binding)
    return event, binding.producer_kind


def validate_compiled_event_derivation(
    root: Path,
    cycle_id: str,
    event: dict[str, Any],
    producer_kind: str,
    initialization: dict[str, Any],
    previous_events: list[dict[str, Any]],
    binding: CompiledEventBinding | None,
) -> None:
    if producer_kind == _STAGE_RESULT.producer_kind:
        if binding is None:
            raise ValueError("compiled stage result lacks its opaque binding")
        validate_stage_result_derivation(
            root,
            cycle_id,
            event,
            _opened_derivation(binding),
            previous_events,
        )
        return
    if producer_kind != _SYSTEM.producer_kind:
        return
    if binding is None:
        raise ValueError("compiled system event lacks its opaque binding")
    from ..stage.specs import TARGET_COMPILE_SPECS
    from ..stage.system_steps import render_context_event, render_system_event
    from ..stage.v2_context import collect_selected_context

    step = str(event.get("step") or "")
    task_id = initialization.get("task_id")
    if step == "context":
        full, model, _metrics = collect_selected_context(
            root,
            cycle_id,
            TARGET_COMPILE_SPECS["authority"],
            max_files=12,
            max_paths=40,
        )
        expected = render_context_event(cycle_id, task_id, full, model)
    else:
        expected = render_system_event(
            cycle_id, step, task_id, previous_events
        )
    semantic = {
        key: item
        for key, item in event.items()
        if key not in {"event_kind", "producer_kind"}
    }
    if canonical_json_bytes(semantic) != canonical_json_bytes(expected):
        raise ValueError(
            "compiled system event does not match deterministic cycle derivation"
        )


__all__ = [
    "CompiledEventBinding",
    "compile_stage_result_binding",
    "open_compiled_event_binding",
]
