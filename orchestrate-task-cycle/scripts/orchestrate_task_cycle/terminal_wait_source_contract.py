"""Final derive and A-to-B-to-C lineage for rebased terminal waits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .selection_decision_receipt import (
    read_bound_json as read_selection_bound_json,
    read_receipt_selection_synthesis,
)
from .selection_tick_baseline import changed_watch_entries
from .selection_tick_contract import validate_selection_tick_v2
from .selection_tick_policy import material_watch_entries
from .selection_tick_premise import VERIFIED_PREMISE_CONTRACT
from .terminal_wait_baseline_store import SHA256, read_bound_json


FINAL_DERIVE_BINDING_FIELDS = (
    "observed_input_manifest_sha256",
    "wake_predicates",
    "watched_evidence_classes",
    "minimum_material_delta",
)
PREDECESSOR_SNAPSHOT_KEYS = {
    "schema_version",
    "artifact_kind",
    "binding_id",
    "task",
    "source_derive",
    "transition_evidence",
    "selection_baseline",
    "authority_subject",
    "predecessor_snapshot_sha256",
}
SNAPSHOT_SELECTION_KEYS = {
    "ref",
    "sha256",
    "packet_id",
    "observed_input_manifest_sha256",
}


def _closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} requires exact fields {sorted(keys)}")
    return value


def _result_projection_sha256(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _validate_predecessor_packet(packet: dict[str, Any]) -> dict[str, str]:
    validate_selection_tick_v2(packet)
    packet_id = packet["packet_id"]
    manifest = packet["observed_input_manifest_sha256"]
    if (
        packet["premise_input_contract"] != VERIFIED_PREMISE_CONTRACT
        or packet["status"] not in {"baseline_recorded", "no_op"}
        or packet["selection_required"] is not False
        or packet["agent_fanout_allowed"] is not False
        or packet["full_cycle_allowed"] is not False
        or packet["mutation_performed"] is not False
        or packet["not_goal_truth"] is not True
        or packet["not_authority"] is not True
    ):
        raise ValueError("predecessor selection baseline is not terminal-safe")
    return {
        "packet_id": packet_id,
        "observed_input_manifest_sha256": manifest,
    }


def _predecessor_selection_packet(
    root: Path, expected_snapshot_sha256: str | None
) -> dict[str, Any]:
    if not isinstance(expected_snapshot_sha256, str) or not SHA256.fullmatch(
        expected_snapshot_sha256
    ):
        raise ValueError("rebased selection requires an exact predecessor snapshot")
    snapshot_ref = (
        f".task/terminal_wait_baseline/snapshots/{expected_snapshot_sha256}.json"
    )
    _, snapshot = read_bound_json(
        root,
        {"ref": snapshot_ref, "sha256": expected_snapshot_sha256},
        "predecessor terminal-wait snapshot",
        expected_ref=snapshot_ref,
    )
    _closed(snapshot, PREDECESSOR_SNAPSHOT_KEYS, "predecessor terminal-wait snapshot")
    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("artifact_kind") != "terminal_wait_selection_baseline_binding"
    ):
        raise ValueError("predecessor terminal-wait snapshot schema is invalid")
    selection = _closed(
        snapshot.get("selection_baseline"),
        SNAPSHOT_SELECTION_KEYS,
        "predecessor selection baseline",
    )
    _, packet = read_bound_json(
        root,
        {"ref": selection["ref"], "sha256": selection["sha256"]},
        "predecessor selection baseline",
    )
    projection = _validate_predecessor_packet(packet)
    if (
        selection["packet_id"] != projection["packet_id"]
        or selection["observed_input_manifest_sha256"]
        != projection["observed_input_manifest_sha256"]
    ):
        raise ValueError("predecessor selection snapshot projection is inconsistent")
    return packet


def _validate_rebased_lineage(
    root: Path,
    source: dict[str, Any],
    packet: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    predecessor = _predecessor_selection_packet(
        root, source.get("expected_current_snapshot_sha256")
    )
    _, trigger = read_selection_bound_json(
        root,
        receipt["trigger_selection_tick"],
        "selection trigger tick",
    )
    validate_selection_tick_v2(trigger)
    if (
        trigger["previous_input_manifest_sha256"]
        != predecessor["observed_input_manifest_sha256"]
        or trigger["changed_watch_entries"]
        != changed_watch_entries(predecessor, trigger["watch_entries"])
        or any(
            trigger[field] != predecessor[field]
            for field in (
                "wake_predicates",
                "watched_evidence_classes",
                "minimum_material_delta",
                "premise_input_contract",
            )
        )
    ):
        raise ValueError("selection trigger does not descend from the predecessor")
    rebased_changes = changed_watch_entries(trigger, packet["watch_entries"])
    rebased_material = material_watch_entries(
        rebased_changes,
        packet["watch_entries"],
        packet["watched_evidence_classes"],
    )
    if (
        packet["previous_input_manifest_sha256"]
        != trigger["observed_input_manifest_sha256"]
        or packet["changed_watch_entries"] != rebased_changes
        or packet["material_changed_watch_entries"] != rebased_material
        or rebased_material
        or packet["changed_evidence_classes"]
        != sorted({row["evidence_class"] for row in rebased_changes})
        or any(
            packet[field] != trigger[field]
            for field in (
                "wake_predicates",
                "watched_evidence_classes",
                "minimum_material_delta",
                "premise_input_contract",
            )
        )
    ):
        raise ValueError("rebased selection baseline does not descend from its trigger")


def _validate_final_terminal_derive(
    root: Path,
    derive: dict[str, Any],
    packet: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    if set(derive) == {"result"}:
        raise ValueError("rebased source derive must be a direct final derive result")
    from .result_contract.api import validate as validate_result_contract

    result = validate_result_contract(
        "derive",
        derive,
        "block",
        {"workspace_root": str(root)},
    )
    if result.get("status") == "block":
        codes = ", ".join(
            sorted(
                {
                    str(row.get("code"))
                    for row in result.get("findings", [])
                    if isinstance(row, dict)
                }
            )
        )
        raise ValueError(f"rebased source derive contract failed: {codes}")
    wait = derive.get("terminal_wait")
    synthesis = read_receipt_selection_synthesis(root, receipt)
    analysis = derive.get("improvement_analysis_manifest")
    embedded_synthesis = (
        analysis.get("synthesis") if isinstance(analysis, dict) else None
    )
    if (
        derive.get("selection_outcome") != "terminal_wait"
        or derive.get("selected_task_source") != "terminal_wait"
        or derive.get("next_task_id") not in (None, "")
        or not isinstance(wait, dict)
        or wait.get("selection_tick_baseline") != packet
        or wait.get("selection_tick_baseline_sha256")
        != _result_projection_sha256(packet)
        or wait.get("last_selection_receipt") != receipt["receipt_id"]
        or any(
            wait.get(field) != packet.get(field)
            for field in FINAL_DERIVE_BINDING_FIELDS
        )
        or analysis != synthesis["improvement_analysis_manifest"]
        or not isinstance(embedded_synthesis, dict)
        or embedded_synthesis.get("selection_outcome") != receipt["outcome"]
        or embedded_synthesis.get("synthesis_receipt_id")
        != receipt["synthesis_receipt_id"]
        or embedded_synthesis.get("input_evidence_manifest_sha256")
        != receipt["input_evidence_manifest_sha256"]
    ):
        raise ValueError(
            "rebased source derive does not bind the final terminal-wait selection"
        )


def validate_rebased_terminal_source(
    root: Path,
    source: dict[str, Any],
    derive: dict[str, Any],
    packet: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    """Validate durable predecessor, trigger, rebase, and final derive lineage."""

    _validate_rebased_lineage(root, source, packet, receipt)
    _validate_final_terminal_derive(root, derive, packet, receipt)


__all__ = ("validate_rebased_terminal_source",)
