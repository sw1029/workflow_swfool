"""Closed persisted receipt for one completed derive-selection decision."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .selection_decision_store import (
    SHA256,
    canonical_bytes,
    canonical_sha256,
    closed_object as _closed,
    normalize_binding,
    read_bound_json,
)
from .selection_synthesis import validate_selection_synthesis
from .selection_tick_contract import validate_selection_tick_v2


RECEIPT_KEYS = {
    "schema_version",
    "artifact_kind",
    "receipt_id",
    "trigger_selection_tick_id",
    "trigger_selection_tick_sha256",
    "trigger_selection_tick",
    "selection_decision",
    "synthesis_receipt_id",
    "input_evidence_manifest_sha256",
    "outcome",
    "selected_task_id",
    "not_goal_truth",
    "not_authority",
    "not_validation_evidence",
    "not_completion_evidence",
    "mutation_performed",
    "receipt_sha256",
}
DECISION_KEYS = {
    "schema_version",
    "artifact_kind",
    "decision_id",
    "decision_stage",
    "trigger_selection_tick_id",
    "trigger_selection_tick_sha256",
    "selection_synthesis",
    "synthesis_receipt_id",
    "outcome",
    "selected_task_id",
    "evidence_manifest_sha256",
    "decision_sha256",
}
OUTCOMES = frozenset(
    {"selected", "terminal_wait", "terminal_blocked", "user_escalation"}
)
PACKET_ID = re.compile(r"selection-tick-[0-9a-f]{32}")
OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


def selection_tick_sha256(packet: dict[str, Any]) -> str:
    return canonical_sha256(packet)


def _trigger_binding(packet: dict[str, Any]) -> dict[str, str]:
    _validate_trigger_tick(packet)
    return {
        "trigger_selection_tick_id": packet["packet_id"],
        "trigger_selection_tick_sha256": selection_tick_sha256(packet),
    }


def _persisted_trigger_binding(
    root: Path,
    trigger_tick: dict[str, Any],
    trigger_tick_binding: dict[str, str],
) -> dict[str, str]:
    persisted = normalize_binding(trigger_tick_binding, "selection trigger tick")
    _, reopened = read_bound_json(root, persisted, "selection trigger tick")
    _validate_trigger_tick(reopened)
    if reopened != trigger_tick:
        raise ValueError("selection trigger binding reopens another tick")
    return persisted


def _normalize_trigger_binding(value: Any) -> dict[str, str]:
    binding = _closed(
        value,
        {"trigger_selection_tick_id", "trigger_selection_tick_sha256"},
        "selection trigger binding",
    )
    trigger_id = binding.get("trigger_selection_tick_id")
    digest = binding.get("trigger_selection_tick_sha256")
    if (
        not isinstance(trigger_id, str)
        or not isinstance(digest, str)
        or not PACKET_ID.fullmatch(trigger_id)
        or not SHA256.fullmatch(digest)
    ):
        raise ValueError("selection trigger binding is invalid")
    return {
        "trigger_selection_tick_id": trigger_id,
        "trigger_selection_tick_sha256": digest,
    }


def _validate_trigger_tick(packet: dict[str, Any]) -> None:
    validate_selection_tick_v2(packet)
    if (
        packet.get("status") != "selection_required"
        or packet.get("selection_required") is not True
        or packet.get("agent_fanout_allowed") is not True
    ):
        raise ValueError("selection decision requires an exact selection-required tick")


def _normalize_outcome(
    outcome_value: object, selected_task_id_value: object
) -> tuple[str, str | None]:
    if not isinstance(outcome_value, str) or outcome_value not in OUTCOMES:
        raise ValueError("derive selection decision has no canonical outcome")
    if selected_task_id_value is not None and not isinstance(
        selected_task_id_value, str
    ):
        raise ValueError("selection decision task ID must be a string or null")
    outcome = outcome_value
    selected_task_id = selected_task_id_value
    if outcome == "selected":
        if (
            selected_task_id is None
            or selected_task_id != selected_task_id.strip()
            or not OPAQUE_ID.fullmatch(selected_task_id)
        ):
            raise ValueError("selected decision requires one bounded next task ID")
    elif selected_task_id is not None:
        raise ValueError("non-selected decision cannot carry a next task ID")
    return outcome, selected_task_id


def _decision_core(
    trigger: dict[str, str],
    selection_synthesis: dict[str, str],
    synthesis_receipt_id: str,
    outcome: str,
    selected_task_id: str | None,
    evidence_manifest_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "preliminary_selection_decision",
        "decision_stage": "preliminary_selection",
        **trigger,
        "selection_synthesis": selection_synthesis,
        "synthesis_receipt_id": synthesis_receipt_id,
        "outcome": outcome,
        "selected_task_id": selected_task_id,
        "evidence_manifest_sha256": evidence_manifest_sha256,
    }


def _read_selection_synthesis(
    root: Path, value: Any
) -> tuple[dict[str, str], dict[str, Any]]:
    synthesis_binding = normalize_binding(value, "selection synthesis")
    _, synthesis_value = read_bound_json(root, synthesis_binding, "selection synthesis")
    return synthesis_binding, validate_selection_synthesis(root, synthesis_value)


def render_preliminary_selection_decision(
    root: Path,
    trigger_tick: dict[str, Any],
    selection_synthesis_binding: dict[str, str],
) -> dict[str, Any]:
    """Render a preliminary decision from one persisted three-lens synthesis."""

    _validate_trigger_tick(trigger_tick)
    synthesis_binding, synthesis = _read_selection_synthesis(
        root, selection_synthesis_binding
    )
    normalized_outcome, normalized_task = _normalize_outcome(
        synthesis["selection_outcome"], synthesis["selected_task_id"]
    )
    core = _decision_core(
        _trigger_binding(trigger_tick),
        synthesis_binding,
        synthesis["synthesis_receipt_id"],
        normalized_outcome,
        normalized_task,
        synthesis["input_evidence_manifest_sha256"],
    )
    decision_id = "preliminary-selection-" + canonical_sha256(core)[:24]
    body = {**core, "decision_id": decision_id}
    return {**body, "decision_sha256": canonical_sha256(body)}


def validate_preliminary_selection_decision(
    root: Path,
    value: Any,
    *,
    expected_trigger_tick: dict[str, Any] | None = None,
    expected_trigger_binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    decision = _closed(value, DECISION_KEYS, "derive selection decision")
    if (
        decision.get("schema_version") != 1
        or decision.get("artifact_kind") != "preliminary_selection_decision"
        or decision.get("decision_stage") != "preliminary_selection"
    ):
        raise ValueError("derive selection decision schema is invalid")
    if (expected_trigger_tick is None) == (expected_trigger_binding is None):
        raise ValueError("derive selection decision requires one exact trigger")
    trigger = (
        _trigger_binding(expected_trigger_tick)
        if expected_trigger_tick is not None
        else _normalize_trigger_binding(expected_trigger_binding)
    )
    outcome, selected_task_id = _normalize_outcome(
        decision.get("outcome"), decision.get("selected_task_id")
    )
    synthesis_binding, synthesis = _read_selection_synthesis(
        root, decision.get("selection_synthesis")
    )
    evidence_digest = synthesis["input_evidence_manifest_sha256"]
    synthesis_receipt_id = synthesis["synthesis_receipt_id"]
    if (
        outcome != synthesis["selection_outcome"]
        or selected_task_id != synthesis["selected_task_id"]
        or decision.get("evidence_manifest_sha256") != evidence_digest
        or decision.get("synthesis_receipt_id") != synthesis_receipt_id
    ):
        raise ValueError("preliminary decision differs from its bound synthesis")
    core = _decision_core(
        trigger,
        synthesis_binding,
        synthesis_receipt_id,
        outcome,
        selected_task_id,
        evidence_digest,
    )
    expected_id = "preliminary-selection-" + canonical_sha256(core)[:24]
    body = {**core, "decision_id": expected_id}
    sealed = {**body, "decision_sha256": canonical_sha256(body)}
    if decision != sealed:
        raise ValueError("derive selection decision integrity check failed")
    return sealed


def _receipt_core(
    trigger: dict[str, str],
    trigger_selection_tick: dict[str, str],
    selection_decision: dict[str, str],
    synthesis_receipt_id: str,
    input_evidence_manifest_sha256: str,
    outcome: str,
    selected_task_id: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "selection_decision_receipt",
        **trigger,
        "trigger_selection_tick": trigger_selection_tick,
        "selection_decision": selection_decision,
        "synthesis_receipt_id": synthesis_receipt_id,
        "input_evidence_manifest_sha256": input_evidence_manifest_sha256,
        "outcome": outcome,
        "selected_task_id": selected_task_id,
        "not_goal_truth": True,
        "not_authority": True,
        "not_validation_evidence": True,
        "not_completion_evidence": True,
        "mutation_performed": False,
    }


def render_selection_decision_receipt(
    root: Path,
    trigger_tick: dict[str, Any],
    trigger_tick_binding: dict[str, str],
    selection_decision_binding: dict[str, str],
) -> dict[str, Any]:
    _validate_trigger_tick(trigger_tick)
    persisted_trigger = _persisted_trigger_binding(
        root, trigger_tick, trigger_tick_binding
    )
    decision_binding = normalize_binding(
        selection_decision_binding, "preliminary selection decision"
    )
    _, decision_value = read_bound_json(
        root, decision_binding, "preliminary selection decision"
    )
    decision = validate_preliminary_selection_decision(
        root, decision_value, expected_trigger_tick=trigger_tick
    )
    outcome = decision["outcome"]
    selected_task_id = decision["selected_task_id"]
    core = _receipt_core(
        _trigger_binding(trigger_tick),
        persisted_trigger,
        decision_binding,
        decision["synthesis_receipt_id"],
        decision["evidence_manifest_sha256"],
        outcome,
        selected_task_id,
    )
    receipt_id = "selection-decision-" + canonical_sha256(core)[:24]
    body = {**core, "receipt_id": receipt_id}
    return {**body, "receipt_sha256": canonical_sha256(body)}


def read_receipt_trigger_tick(root: Path, value: Any) -> dict[str, Any]:
    """Reopen and validate the exact selection tick embedded by one receipt."""

    receipt = _closed(value, RECEIPT_KEYS, "selection decision receipt")
    trigger = _normalize_trigger_binding(
        {
            "trigger_selection_tick_id": receipt.get("trigger_selection_tick_id"),
            "trigger_selection_tick_sha256": receipt.get(
                "trigger_selection_tick_sha256"
            ),
        }
    )
    persisted = normalize_binding(
        receipt.get("trigger_selection_tick"), "selection trigger tick"
    )
    _, reopened = read_bound_json(root, persisted, "selection trigger tick")
    _validate_trigger_tick(reopened)
    if _trigger_binding(reopened) != trigger:
        raise ValueError("selection decision receipt trigger bytes disagree")
    return reopened


def validate_selection_decision_receipt(
    root: Path,
    value: Any,
    *,
    expected_trigger_tick: dict[str, Any] | None = None,
    expected_trigger_binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    receipt = _closed(value, RECEIPT_KEYS, "selection decision receipt")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("artifact_kind") != "selection_decision_receipt"
    ):
        raise ValueError("selection decision receipt schema is invalid")
    if (expected_trigger_tick is None) == (expected_trigger_binding is None):
        raise ValueError("selection decision receipt requires one exact trigger")
    trigger = (
        _trigger_binding(expected_trigger_tick)
        if expected_trigger_tick is not None
        else _normalize_trigger_binding(expected_trigger_binding)
    )
    trigger_id = receipt.get("trigger_selection_tick_id")
    trigger_sha256 = receipt.get("trigger_selection_tick_sha256")
    if (
        not isinstance(trigger_id, str)
        or not isinstance(trigger_sha256, str)
        or not PACKET_ID.fullmatch(trigger_id)
        or not SHA256.fullmatch(trigger_sha256)
    ):
        raise ValueError("selection decision trigger binding is invalid")
    if (
        trigger_id != trigger["trigger_selection_tick_id"]
        or trigger_sha256 != trigger["trigger_selection_tick_sha256"]
    ):
        raise ValueError("selection decision receipt binds another trigger tick")
    persisted_trigger = normalize_binding(
        receipt.get("trigger_selection_tick"), "selection trigger tick"
    )
    reopened_trigger = read_receipt_trigger_tick(root, receipt)
    if expected_trigger_tick is not None and reopened_trigger != expected_trigger_tick:
        raise ValueError("selection decision receipt reopens another trigger tick")
    decision_binding = normalize_binding(
        receipt.get("selection_decision"), "preliminary selection decision"
    )
    _, decision_value = read_bound_json(
        root, decision_binding, "preliminary selection decision"
    )
    decision = validate_preliminary_selection_decision(
        root, decision_value, expected_trigger_binding=trigger
    )
    outcome = decision["outcome"]
    selected_task_id = decision["selected_task_id"]
    core = _receipt_core(
        trigger,
        persisted_trigger,
        decision_binding,
        decision["synthesis_receipt_id"],
        decision["evidence_manifest_sha256"],
        outcome,
        selected_task_id,
    )
    expected_id = "selection-decision-" + canonical_sha256(core)[:24]
    body = {**core, "receipt_id": expected_id}
    sealed = {**body, "receipt_sha256": canonical_sha256(body)}
    if receipt != sealed:
        raise ValueError("selection decision receipt integrity check failed")
    return sealed


def read_selection_decision_receipt(
    root: Path,
    receipt_binding: dict[str, str],
    *,
    expected_trigger_tick: dict[str, Any] | None = None,
    expected_trigger_binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    _, receipt = read_bound_json(root, receipt_binding, "selection decision receipt")
    return validate_selection_decision_receipt(
        root,
        receipt,
        expected_trigger_tick=expected_trigger_tick,
        expected_trigger_binding=expected_trigger_binding,
    )


def read_receipt_selection_synthesis(
    root: Path, receipt: dict[str, Any]
) -> dict[str, Any]:
    """Reopen the durable 3-lens synthesis bound by a validated receipt."""

    validated_receipt = _closed(receipt, RECEIPT_KEYS, "selection decision receipt")
    _, decision_value = read_bound_json(
        root,
        normalize_binding(
            validated_receipt["selection_decision"],
            "preliminary selection decision",
        ),
        "preliminary selection decision",
    )
    decision = validate_preliminary_selection_decision(
        root,
        decision_value,
        expected_trigger_binding={
            "trigger_selection_tick_id": validated_receipt["trigger_selection_tick_id"],
            "trigger_selection_tick_sha256": validated_receipt[
                "trigger_selection_tick_sha256"
            ],
        },
    )
    _, synthesis = _read_selection_synthesis(root, decision["selection_synthesis"])
    return synthesis


def acknowledgement_binding(
    receipt_binding: dict[str, str], receipt: dict[str, Any]
) -> dict[str, Any]:
    persisted = normalize_binding(receipt_binding, "selection decision receipt")
    validated = _closed(receipt, RECEIPT_KEYS, "selection decision receipt")
    return {
        "trigger_tick_id": validated["trigger_selection_tick_id"],
        "trigger_tick_sha256": validated["trigger_selection_tick_sha256"],
        "selection_receipt_id": validated["receipt_id"],
        "selection_receipt_ref": persisted["ref"],
        "selection_receipt_sha256": persisted["sha256"],
        "selection_receipt_integrity_sha256": validated["receipt_sha256"],
        "selection_outcome": validated["outcome"],
        "selected_task_id": validated["selected_task_id"],
    }


__all__ = (
    "DECISION_KEYS",
    "RECEIPT_KEYS",
    "acknowledgement_binding",
    "canonical_bytes",
    "canonical_sha256",
    "normalize_binding",
    "read_bound_json",
    "read_receipt_trigger_tick",
    "read_receipt_selection_synthesis",
    "read_selection_decision_receipt",
    "render_preliminary_selection_decision",
    "render_selection_decision_receipt",
    "selection_tick_sha256",
    "validate_preliminary_selection_decision",
    "validate_selection_decision_receipt",
)
