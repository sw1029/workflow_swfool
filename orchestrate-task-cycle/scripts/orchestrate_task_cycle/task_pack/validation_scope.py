"""Scope-fidelity and measurable-acceptance checks for one item."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..acceptance_contract import acceptance_verifier_contract
from .packet_io import non_empty, scope_fidelity_records, truthy
from .prerequisite_chain import validate_item_prerequisite_chain
from .validation_acceptance import (
    validate_evidence_acceptance,
    validate_residual_acceptance,
    validate_verifier_acceptance,
)

FindingAdder = Callable[..., None]


def validate_item_scope(
    item: dict[str, Any],
    item_id: str,
    result: dict[str, Any],
    residual_links: list[tuple[str, str]],
    add: FindingAdder,
) -> None:
    validate_item_prerequisite_chain(item, item_id, result, add)
    records, valid_scope_shape = scope_fidelity_records(item)
    if not valid_scope_shape:
        add("block", "scope_fidelity_invalid", "`scope_fidelity` must be an object or a list of objects.", {"item_id": item_id})
        records = []
    for record_index, record in enumerate(records):
        directive_id = str(record.get("directive_id") or "").strip()
        original_target = record.get("original_target", record.get("measurable_target"))
        item_acceptance = record.get("item_acceptance", item.get("acceptance"))
        has_target = non_empty(original_target)
        narrowed = truthy(record.get("narrowed"))
        residual_item_id = str(record.get("residual_item_id") or "").strip()
        verifier_contract = acceptance_verifier_contract(
            record
        ) or acceptance_verifier_contract(item)

        if has_target and not directive_id:
            add(
                "block",
                "scope_fidelity_directive_id_missing",
                "Measurable scope_fidelity records require `directive_id`.",
                {"item_id": item_id, "record_index": record_index},
            )
        if has_target and not non_empty(item_acceptance):
            add(
                "block",
                "scope_fidelity_item_acceptance_missing",
                "Measurable scope_fidelity records require item acceptance copied from or traceable to the directive target.",
                {"item_id": item_id, "directive_id": directive_id or None},
            )
        if narrowed:
            if not non_empty(record.get("narrow_reason")):
                add(
                    "block",
                    "scope_fidelity_narrow_reason_missing",
                    "Narrowed measurable directives require `narrow_reason`.",
                    {"item_id": item_id, "directive_id": directive_id or None},
                )
            if not residual_item_id:
                add(
                    "block",
                    "scope_fidelity_residual_item_missing",
                    "Narrowed measurable directives require `residual_item_id` so remaining scope stays open.",
                    {"item_id": item_id, "directive_id": directive_id or None},
                )
            else:
                residual_links.append((item_id, residual_item_id))

        if has_target and item.get("status") == "consumed":
            acceptance_gate = result.get("acceptance_provenance_gate") if isinstance(result.get("acceptance_provenance_gate"), dict) else {}
            acceptance_gate = acceptance_gate or (result.get("scope_fidelity_gate") if isinstance(result.get("scope_fidelity_gate"), dict) else {})
            if not acceptance_gate:
                add(
                    "block",
                    "acceptance_provenance_gate_missing",
                    "Consumed measurable pack items require an `acceptance_provenance_gate` result comparing actual achievement to the original directive target.",
                    {"item_id": item_id, "directive_id": directive_id or None},
                )
                continue
            if truthy(acceptance_gate.get("acceptance_diluted")):
                add(
                    "block",
                    "acceptance_diluted_item_consumed",
                    "A pack item with `acceptance_diluted=true` cannot be `consumed`; keep the residual target open and mark validation partial.",
                    {"item_id": item_id, "directive_id": directive_id or None},
                )
            target_met = truthy(acceptance_gate.get("target_met"))
            explicit_descope = truthy(acceptance_gate.get("explicit_descope_decision"))
            if not target_met and not explicit_descope:
                add(
                    "block",
                    "measurable_target_unmet_without_descope",
                    "Consumed measurable pack items must meet the original target or record an explicit descope decision with residual scope.",
                    {"item_id": item_id, "directive_id": directive_id or None},
                )
            validate_verifier_acceptance(
                record, item, result, verifier_contract, explicit_descope, item_id, directive_id, add
            )
            validate_evidence_acceptance(item, result, explicit_descope, item_id, directive_id, add)
            validate_residual_acceptance(record, item, result, explicit_descope, item_id, directive_id, add)
