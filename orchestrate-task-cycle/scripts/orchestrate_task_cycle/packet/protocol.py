"""Sealed protocol-v1 authority for legacy full-packet rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..ledger.constants import COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE
from ..ledger.support import read_initialization_metadata, validate_cycle_id
from ..ledger.workflow_contract import workflow_contract_state


def packet_cycle_contract(
    context: dict[str, Any], stage: dict[str, Any]
) -> dict[str, Any]:
    """Resolve only the exact cycle initialization needed by the packet gate."""

    workspace_value = context.get("workspace")
    cycle_state = (
        context.get("cycle_state")
        if isinstance(context.get("cycle_state"), dict)
        else {}
    )
    stage_cycle = stage.get("cycle_id")
    context_cycle = cycle_state.get("latest_cycle_id")
    current_stage = (
        cycle_state.get("current_stage")
        if isinstance(cycle_state.get("current_stage"), dict)
        else {}
    )
    projected_cycle = current_stage.get("cycle_id")
    supplied_cycles = [
        str(value)
        for value in (stage_cycle, context_cycle, projected_cycle)
        if value is not None and str(value).strip()
    ]
    if len(set(supplied_cycles)) > 1:
        return {"status": "invalid_cycle_context"}
    cycle_value = supplied_cycles[0] if supplied_cycles else None
    if not workspace_value or not cycle_value:
        return {"status": "unbound"}
    try:
        root = Path(str(workspace_value)).expanduser().resolve(strict=True)
        cycle_id = validate_cycle_id(str(cycle_value))
    except (FileNotFoundError, ValueError):
        return {"status": "invalid_cycle_context"}
    try:
        metadata = read_initialization_metadata(root, cycle_id)
    except (OSError, UnicodeError, ValueError):
        return {"status": "invalid_cycle_context", "cycle_id": cycle_id}
    latest_event = (
        current_stage.get("latest_event")
        if isinstance(current_stage.get("latest_event"), dict)
        else {}
    )
    supplied_tasks = [
        str(value)
        for value in (
            stage.get("task_id"),
            context.get("task_id"),
            cycle_state.get("task_id"),
            latest_event.get("task_id"),
        )
        if value is not None and str(value).strip()
    ]
    initialized_task = metadata.get("task_id")
    if (
        initialized_task is not None
        and any(value != str(initialized_task) for value in supplied_tasks)
    ):
        return {"status": "invalid_cycle_context", "cycle_id": cycle_id}
    state = workflow_contract_state(metadata)
    if state == "enforced":
        return {
            "status": "compiler_first_enforced",
            "cycle_id": cycle_id,
            "workflow_contract_profile": COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE,
        }
    return {"status": state, "cycle_id": cycle_id}


def _legacy_packet_permit_support() -> tuple[
    Callable[[dict[str, Any], dict[str, Any]], object],
    Callable[[object, dict[str, Any], dict[str, Any]], None],
]:
    """Keep the permit type and capability out of the importable module surface."""

    capability = object()

    class LegacyPacketPermit:
        __slots__ = ("capability", "cycle_id", "workspace")

        def __init__(
            self, workspace: str, cycle_id: str, supplied_capability: object
        ) -> None:
            self.workspace = workspace
            self.cycle_id = cycle_id
            self.capability = supplied_capability

    def require_legacy_contract(
        context: dict[str, Any], stage: dict[str, Any]
    ) -> dict[str, Any]:
        contract = packet_cycle_contract(context, stage)
        if contract["status"] in {
            "compiler_first_enforced",
            "historical_v2_read_only",
            "invalid",
        }:
            raise ValueError(
                "generic full packet rendering is disabled for protocol-v2 "
                "cycles; new cycles must use `stage prepare` and historical "
                "unmarked v2 cycles are read-only; invalid cycle contracts "
                "also fail closed"
            )
        if contract["status"] != "protocol_v1_unchanged":
            raise ValueError(
                "generic full packet rendering requires an explicitly bound "
                "legacy cycle"
            )
        return contract

    def mint(
        context: dict[str, Any], stage: dict[str, Any]
    ) -> object:
        contract = require_legacy_contract(context, stage)
        workspace = str(
            Path(str(context["workspace"]))
            .expanduser()
            .resolve(strict=True)
        )
        return LegacyPacketPermit(
            workspace,
            str(contract["cycle_id"]),
            capability,
        )

    def validate(
        permit: object,
        context: dict[str, Any],
        stage: dict[str, Any],
    ) -> None:
        if (
            not isinstance(permit, LegacyPacketPermit)
            or permit.capability is not capability
        ):
            raise ValueError(
                "direct PacketBuilder use requires an opaque verified "
                "protocol-v1 permit"
            )
        contract = require_legacy_contract(context, stage)
        workspace = str(
            Path(str(context["workspace"]))
            .expanduser()
            .resolve(strict=True)
        )
        if (
            permit.workspace != workspace
            or permit.cycle_id != contract["cycle_id"]
        ):
            raise ValueError(
                "legacy packet permit does not match the selected cycle"
            )

    return mint, validate


(
    _mint_legacy_packet_permit,
    _validate_legacy_packet_permit,
) = _legacy_packet_permit_support()
del _legacy_packet_permit_support


__all__ = ["packet_cycle_contract"]
