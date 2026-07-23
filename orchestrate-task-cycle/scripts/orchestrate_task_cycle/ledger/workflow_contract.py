"""Compiler-first ledger write boundary for newly initialized protocol-v2 cycles."""

from __future__ import annotations

from typing import Any

from .constants import (
    COMPILED_STAGE_OBSERVATION_EVENT_KIND,
    COMPILED_STAGE_RESULT_EVENT_KIND,
    COMPILED_SYSTEM_EVENT_KIND,
    COMPILED_TERMINAL_LIFECYCLE_EVENT_KIND,
    COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE,
)


PRODUCER_EVENT_KINDS = {
    "stage_result_compiler": COMPILED_STAGE_RESULT_EVENT_KIND,
    "system_event_compiler": COMPILED_SYSTEM_EVENT_KIND,
    "stage_observer": COMPILED_STAGE_OBSERVATION_EVENT_KIND,
    "terminal_lifecycle_compiler": COMPILED_TERMINAL_LIFECYCLE_EVENT_KIND,
}
PUBLIC_PRODUCER = "public_direct_append"
SYSTEM_STEPS = {"context", "route_plan", "result_contract", "ledger_append"}
PROVENANCE_VERSION_FIELD = "initialization_provenance_version"


def workflow_contract_state(metadata: dict[str, Any]) -> str:
    profile = metadata.get("workflow_contract_profile")
    protocol = metadata.get("stage_compiler_protocol_version")
    sealed = metadata.get(PROVENANCE_VERSION_FIELD) == 1
    if profile == COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE:
        return "enforced" if protocol == 2 and sealed else "invalid"
    if profile is not None:
        return "invalid"
    if protocol == 2:
        return "historical_v2_read_only"
    if protocol == 1:
        return "protocol_v1_unchanged" if sealed else "historical_v1_read_only"
    return "invalid"


def validate_ledger_producer(
    metadata: dict[str, Any],
    event: dict[str, Any],
    producer_kind: str,
) -> dict[str, Any] | None:
    """Validate one write against its immutable cycle contract."""

    state = workflow_contract_state(metadata)
    if state == "enforced":
        if producer_kind == PUBLIC_PRODUCER:
            raise ValueError(
                "compiler-first cycle rejects public direct ledger append; "
                "use a typed internal producer"
            )
        expected_kind = PRODUCER_EVENT_KINDS.get(producer_kind)
        if expected_kind is None:
            raise ValueError(f"unregistered compiler-first ledger producer: {producer_kind}")
        if event.get("event_kind") != expected_kind:
            raise ValueError(
                f"ledger producer `{producer_kind}` requires event_kind `{expected_kind}`"
            )
        step = str(event.get("step") or "")
        if producer_kind == "system_event_compiler" and step not in SYSTEM_STEPS:
            raise ValueError("system-event compiler cannot publish an owner stage")
        if producer_kind == "stage_result_compiler" and step in SYSTEM_STEPS:
            raise ValueError("stage-result compiler cannot publish a system stage")
        if producer_kind == "stage_observer" and step != "run":
            raise ValueError("stage observer may publish only the canonical run stage")
        if producer_kind == "terminal_lifecycle_compiler" and step != "report":
            raise ValueError(
                "terminal-lifecycle compiler may publish only the canonical report stage"
            )
        initialized_task_id = metadata.get("task_id")
        event_task_id = event.get("task_id")
        if initialized_task_id is None:
            if event_task_id is not None and str(event_task_id).strip():
                raise ValueError(
                    "compiler-first bootstrap event cannot invent a task_id"
                )
        elif event_task_id is not None and (
            str(event_task_id).strip() != str(initialized_task_id)
        ):
            raise ValueError(
                "compiler-first event task_id differs from cycle initialization"
            )
        if producer_kind == "stage_observer" and (
            event_task_id is None or not str(event_task_id).strip()
        ):
            raise ValueError(
                "compiler-first stage observer requires the initialized task_id"
            )
        return None
    if state == "historical_v1_read_only":
        raise ValueError(
            "historical unsealed protocol-v1 cycles are read-only; "
            "publish immutable migration proof or initialize a new cycle"
        )
    if state == "historical_v2_read_only":
        raise ValueError(
            "historical unmarked protocol-v2 cycles are read-only; "
            "initialize a new compiler-first cycle"
        )
    if state == "protocol_v1_unchanged":
        return None
    raise ValueError("cycle workflow contract metadata is invalid")


def require_cycle_mutation_contract(
    metadata: dict[str, Any], operation: str
) -> str:
    state = workflow_contract_state(metadata)
    if state == "historical_v1_read_only":
        raise ValueError(
            "historical unsealed protocol-v1 cycles are read-only; "
            f"`{operation}` requires immutable migration proof"
        )
    if state == "historical_v2_read_only":
        raise ValueError(
            "historical unmarked protocol-v2 cycles are read-only; "
            f"`{operation}` requires a new compiler-first cycle"
        )
    if state == "invalid":
        raise ValueError("cycle workflow contract metadata is invalid")
    return state


__all__ = [
    "PRODUCER_EVENT_KINDS",
    "PUBLIC_PRODUCER",
    "require_cycle_mutation_contract",
    "validate_ledger_producer",
    "workflow_contract_state",
]
