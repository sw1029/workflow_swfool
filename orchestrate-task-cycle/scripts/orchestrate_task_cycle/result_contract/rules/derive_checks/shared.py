from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ....task_pack import api as task_pack_queue

from ...base import RuleContext, TargetContractRule
from ...common import (
    ADOPTION_AXIS_TASK_KINDS,
    BLOCKER_CONTRACT_REPAIR_TASK_KINDS,
    CANONICAL_PACK_DISPOSITIONS,
    CLASSIFICATION_REPAIR_TASK_KINDS,
    COLLECTION_CONSUMPTION_TASK_KINDS,
    COMMAND_PROVENANCE_TASK_KINDS,
    CONTRACT_SATISFIABILITY_TASK_KINDS,
    CURRENT_LANE_TASK_KINDS,
    CYCLE_REACHABILITY_TASK_KINDS,
    DECISION_FRESHNESS_TASK_KINDS,
    EXECUTION_PRODUCING_TASK_KINDS,
    EXECUTION_STARVATION_TASK_KINDS,
    DERIVE_AGENT_ROLES,
    DERIVE_SELECTION_OUTCOMES,
    ENVELOPE_THAW_TASK_KINDS,
    EXPECTATION_REBASELINE_TASK_KINDS,
    HARVEST_GATE_TASK_KINDS,
    INSTRUMENTATION_TASK_KINDS,
    LEGACY_PACK_DISPOSITION_ALIASES,
    METRIC_BASIS_TASK_KINDS,
    PACK_DISPOSITIONS,
    PACK_MUTATION_DISPOSITIONS,
    PARITY_AXIS_TASK_KINDS,
    PORTFOLIO_QUOTA_TASK_KINDS,
    PRODUCER_SUPPLY_TASK_KINDS,
    PRODUCER_RECONCILIATION_TASK_KINDS,
    REHARVEST_TASK_KINDS,
    REPORT_KEY_REPAIR_TASK_KINDS,
    RESOLUTION_REPAIR_TASK_KINDS,
    SCENARIO_REPAIR_TASK_KINDS,
    SCENARIO_SUPPLY_TASK_KINDS,
    STOCHASTIC_CONTRACT_TASK_KINDS,
    SURFACE_FIELD_TASK_KINDS,
    active_task_pack_present,
    add,
    advice_handling_rationale_present,
    allowed_task_kinds_from_basis,
    boolish,
    first_present,
    float_value,
    forced_task_kind,
    has_value,
    list_values,
    non_empty,
    nonzero_scalar,
    number_value,
    selected_disposition,
    selected_task_kind_value,
    task_pack_in_scope,
    value_for,
)


HANDOFF_APPLICABILITY = {"required", "not_applicable", "missing_required"}
OPAQUE_ID_MAX_LENGTH = 128
EXECUTION_STARVATION_STATUSES = {
    "present",
    "absent",
    "scope_unknown",
    "not_applicable",
}
EXECUTION_SCOPE_RECOVERY_TASK_KINDS = (
    INSTRUMENTATION_TASK_KINDS
    | CLASSIFICATION_REPAIR_TASK_KINDS
    | BLOCKER_CONTRACT_REPAIR_TASK_KINDS
)


def _bounded_opaque_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > OPAQUE_ID_MAX_LENGTH:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        return None
    return text


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _declared_values(data: dict[str, object], paths: tuple[str, ...]) -> list[object]:
    """Return every explicitly declared path, including empty/malformed values."""
    values: list[object] = []
    for path in paths:
        current: object = data
        declared = True
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                declared = False
                break
            current = current[part]
        if declared:
            values.append(current)
    return values


def _bounded_id_items(value: object) -> tuple[set[str], bool]:
    if not isinstance(value, list):
        return set(), False
    items = [normalized for item in value if (normalized := _bounded_opaque_id(item)) is not None]
    return set(items), len(items) == len(value) and len(items) == len(set(items))


def _workspace_root(context: RuleContext) -> Path:
    contract_context = context.get("contract_context")
    values: list[object] = []
    if isinstance(contract_context, dict):
        values.extend((contract_context.get("workspace_root"), contract_context.get("root")))
    values.extend((context.result.get("workspace_root"), context.result.get("root")))
    value = next((item for item in values if isinstance(item, str) and item.strip()), ".")
    return Path(str(value)).resolve()


def _file_digest(root: Path, value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw or raw.startswith(("store:", "opaque:")):
        return None
    path = Path(raw)
    if path.is_absolute():
        return None
    try:
        resolved = (root / path).resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    if not resolved.is_file():
        return None
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_packet(root: Path, value: object) -> tuple[str, dict[str, object]] | None:
    digest = _file_digest(root, value)
    if digest is None:
        return None
    path = (root / Path(str(value))).resolve()
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    payload = body.get("result") if isinstance(body.get("result"), dict) else body
    return digest, payload


def _packet_scalar(packet: dict[str, object], *paths: str) -> object:
    for path in paths:
        current: object = packet
        for part in path.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current not in (None, "", [], {}):
            return current
    return None


# Keep the former monolithic module's compatibility surface deliberate.  In
# particular, the private helpers below were importable from ``rules.derive``
# before the rule was split into ordered stages.
__all__ = (
    "ADOPTION_AXIS_TASK_KINDS",
    "BLOCKER_CONTRACT_REPAIR_TASK_KINDS",
    "CANONICAL_PACK_DISPOSITIONS",
    "CLASSIFICATION_REPAIR_TASK_KINDS",
    "COLLECTION_CONSUMPTION_TASK_KINDS",
    "COMMAND_PROVENANCE_TASK_KINDS",
    "CONTRACT_SATISFIABILITY_TASK_KINDS",
    "CURRENT_LANE_TASK_KINDS",
    "CYCLE_REACHABILITY_TASK_KINDS",
    "DECISION_FRESHNESS_TASK_KINDS",
    "DERIVE_AGENT_ROLES",
    "DERIVE_SELECTION_OUTCOMES",
    "ENVELOPE_THAW_TASK_KINDS",
    "EXECUTION_PRODUCING_TASK_KINDS",
    "EXECUTION_SCOPE_RECOVERY_TASK_KINDS",
    "EXECUTION_STARVATION_TASK_KINDS",
    "EXECUTION_STARVATION_STATUSES",
    "EXPECTATION_REBASELINE_TASK_KINDS",
    "HANDOFF_APPLICABILITY",
    "HARVEST_GATE_TASK_KINDS",
    "INSTRUMENTATION_TASK_KINDS",
    "LEGACY_PACK_DISPOSITION_ALIASES",
    "METRIC_BASIS_TASK_KINDS",
    "OPAQUE_ID_MAX_LENGTH",
    "PACK_DISPOSITIONS",
    "PACK_MUTATION_DISPOSITIONS",
    "PARITY_AXIS_TASK_KINDS",
    "PORTFOLIO_QUOTA_TASK_KINDS",
    "PRODUCER_SUPPLY_TASK_KINDS",
    "PRODUCER_RECONCILIATION_TASK_KINDS",
    "Path",
    "REHARVEST_TASK_KINDS",
    "REPORT_KEY_REPAIR_TASK_KINDS",
    "RESOLUTION_REPAIR_TASK_KINDS",
    "RuleContext",
    "SCENARIO_REPAIR_TASK_KINDS",
    "SCENARIO_SUPPLY_TASK_KINDS",
    "STOCHASTIC_CONTRACT_TASK_KINDS",
    "SURFACE_FIELD_TASK_KINDS",
    "TargetContractRule",
    "_bounded_id_items",
    "_bounded_opaque_id",
    "_declared_values",
    "_file_digest",
    "_local_packet",
    "_nonnegative_int",
    "_packet_scalar",
    "_workspace_root",
    "active_task_pack_present",
    "add",
    "advice_handling_rationale_present",
    "allowed_task_kinds_from_basis",
    "annotations",
    "boolish",
    "first_present",
    "float_value",
    "forced_task_kind",
    "has_value",
    "hashlib",
    "json",
    "list_values",
    "non_empty",
    "nonzero_scalar",
    "number_value",
    "selected_disposition",
    "selected_task_kind_value",
    "task_pack_in_scope",
    "task_pack_queue",
    "value_for",
)
