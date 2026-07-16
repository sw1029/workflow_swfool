from __future__ import annotations

from pathlib import Path
from typing import Any

from . import orchestration as _orchestration

def load_verified_finalized_loopback_state(
    root: Path,
    cycle_id: str,
) -> tuple[dict[str, Any], str, str | None]:
    """Load replayable loopback projections through the finalizer's verifier."""
    pointer = root / ".task" / "cycle" / str(cycle_id) / "current_finalization.json"
    if not pointer.is_file():
        return {}, "not_available", None
    try:
        verified = _orchestration.load_current_finalized_state(root, str(cycle_id))
    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return {}, "invalid", f"{type(exc).__name__}:{exc}"
    if not isinstance(verified, dict) or verified.get("valid") is not True:
        return {}, "invalid", "finalized_state_not_verified"
    durable_state = verified.get("durable_state_candidate")
    projections: dict[str, Any] = {}
    if isinstance(durable_state, dict) and durable_state.get("mode") == "complete_projection":
        raw = durable_state.get("projections")
        if isinstance(raw, dict):
            projections = dict(raw)
    elif isinstance(durable_state, dict) and durable_state.get("mode") == "typed_operations":
        for operation in durable_state.get("operations") or []:
            if not isinstance(operation, dict):
                continue
            target_id = str(operation.get("target_id") or "")
            payload = operation.get("payload")
            if target_id and isinstance(payload, dict):
                projections[target_id] = payload
    else:
        return {}, "invalid", "finalized_durable_state_mode_invalid"
    return {
        "verified_state": verified,
        "projections": projections,
    }, "verified", None

def finalized_projection_rows(projections: dict[str, Any], target_id: str) -> tuple[list[dict[str, Any]], bool]:
    aliases = {
        "family_progress_registry": ("family_progress_registry", "registry_projection"),
        "root_cause_ledger": ("root_cause_ledger", "ledger_projection"),
    }
    for key in aliases.get(target_id, (target_id,)):
        value = projections.get(key)
        if isinstance(value, dict) and isinstance(value.get("rows"), list):
            value = value["rows"]
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)], True
        if isinstance(value, dict):
            return [value], True
    return [], False

def finalized_seal_projection(projections: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    value = projections.get("sealed_blocker_families")
    if isinstance(value, dict) and isinstance(value.get("state"), dict):
        value = value["state"]
    return (dict(value), True) if isinstance(value, dict) else ({}, False)
