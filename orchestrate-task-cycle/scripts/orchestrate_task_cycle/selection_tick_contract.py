"""Closed structural contract shared by selection-tick producers and consumers."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any

from .selection_tick_premise import (
    PREMISE_CONTRACTS,
    VERIFIED_PREMISE_CONTRACT,
    validate_embedded_verified_premise_row,
)
from .selection_tick_causal_contract import validate_tick_causality
from .selection_tick_limits import (
    MAX_AUTHORITY_SCOPES,
    MAX_CARRIED_WATCH_IDS,
    MAX_CHANGE_ENTRIES,
    MAX_PENDING_PUBLICATIONS,
    MAX_POLICY_IDS,
    MAX_WATCH_ENTRIES,
)
from .selection_tick_policy import EVIDENCE_CLASSES, material_watch_entries


V2_PACKET_KEYS = {
    "format_version",
    "artifact_kind",
    "status",
    "reason",
    "observed_input_manifest_sha256",
    "previous_input_manifest_sha256",
    "watch_entries",
    "changed_watch_entries",
    "changed_evidence_classes",
    "material_changed_watch_entries",
    "wake_predicates",
    "wake_evaluation_rule",
    "wake_predicate_ids_are_policy_labels",
    "watched_evidence_classes",
    "minimum_material_delta",
    "premise_input_contract",
    "satisfied_wake_predicates",
    "exact_premise_supplied",
    "fresh_exact_premise_detected",
    "carried_forward_watch_ids",
    "acknowledgement_requested_for_packet_id",
    "selection_acknowledgement_binding",
    "selection_acknowledgement_status",
    "acknowledged_selection_tick_id",
    "baseline_rebased",
    "authority_scope_ids",
    "selection_required",
    "agent_fanout_allowed",
    "full_cycle_allowed",
    "next_action",
    "pending_selection_publication_ids",
    "selection_publication_status",
    "not_goal_truth",
    "not_authority",
    "mutation_performed",
    "packet_id",
}
ACKNOWLEDGEMENT_KEYS = {
    "trigger_tick_id",
    "trigger_tick_sha256",
    "selection_receipt_id",
    "selection_receipt_ref",
    "selection_receipt_sha256",
    "selection_receipt_integrity_sha256",
    "selection_outcome",
    "selected_task_id",
}
STATUSES = {
    "baseline_recorded",
    "no_op",
    "selection_required",
    "recovery_required",
    "drift_blocked",
}
ACK_STATUSES = {
    "not_requested",
    "accepted",
    "rejected_input_drift",
    "blocked_publication",
}
SELECTION_OUTCOMES = {
    "selected",
    "terminal_wait",
    "terminal_blocked",
    "user_escalation",
}
RAW_PREMISE_FORBIDDEN_KEYS = {
    "premise_input_contract",
    "premise_receipt_schema_version",
    "premise_receipt_id",
    "premise_replay_identity_sha256",
    "premise_receipt",
}
SHA256 = re.compile(r"[0-9a-f]{64}")
PACKET_ID = re.compile(r"selection-tick-[0-9a-f]{32}")
WATCH_ID = re.compile(r"watch-[0-9a-f]{24}")
OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _ids(value: object, label: str, *, max_count: int) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > max_count
        or any(
            not isinstance(item, str) or not OPAQUE_ID.fullmatch(item) for item in value
        )
    ):
        raise ValueError(f"selection tick {label} must contain opaque IDs")
    rows = list(value)
    if len(rows) != len(set(rows)):
        raise ValueError(f"selection tick {label} contains duplicate IDs")
    return rows


def _watch_rows(value: object, premise_contract: str) -> list[dict[str, Any]]:
    if (
        not isinstance(value, list)
        or len(value) > MAX_WATCH_ENTRIES
        or any(not isinstance(row, dict) for row in value)
    ):
        raise ValueError("selection tick watch_entries must be objects")
    rows: list[dict[str, Any]] = list(value)
    ids = [row.get("watch_id") for row in rows]
    if any(
        not isinstance(item, str) or not WATCH_ID.fullmatch(item) for item in ids
    ) or len(ids) != len(set(ids)):
        raise ValueError("selection tick watch IDs are invalid or duplicated")
    for row in rows:
        evidence_class = row.get("evidence_class")
        if (
            not isinstance(evidence_class, str)
            or evidence_class not in EVIDENCE_CLASSES
        ):
            raise ValueError("selection tick watch row evidence_class is unsupported")
        if (evidence_class == "exact_subject") is not (
            row.get("kind") == "exact_premise"
        ):
            raise ValueError("exact-subject evidence requires exact-premise kind")
        if (evidence_class == "authority") is not (
            row.get("kind") == "effective_authority"
        ):
            raise ValueError("authority evidence requires effective-authority kind")
        if evidence_class != "exact_subject":
            if row.get("kind") == "effective_authority" and (
                not isinstance(row.get("authority_scope_id"), str)
                or not OPAQUE_ID.fullmatch(row["authority_scope_id"])
            ):
                raise ValueError("selection tick authority scope ID is invalid")
            continue
        if premise_contract == VERIFIED_PREMISE_CONTRACT:
            validate_embedded_verified_premise_row(row)
        elif any(key in row for key in RAW_PREMISE_FORBIDDEN_KEYS):
            raise ValueError("raw exact-premise row carries verified receipt fields")
    return rows


def _change_rows(value: object, label: str) -> list[dict[str, str]]:
    keys = {"watch_id", "evidence_class", "change_kind"}
    if not isinstance(value, list) or len(value) > MAX_CHANGE_ENTRIES:
        raise ValueError(f"selection tick {label} must be a list")
    rows: list[dict[str, str]] = []
    for row in value:
        evidence_class = row.get("evidence_class") if isinstance(row, dict) else None
        watch_id = row.get("watch_id") if isinstance(row, dict) else None
        if (
            not isinstance(row, dict)
            or set(row) != keys
            or not isinstance(watch_id, str)
            or not WATCH_ID.fullmatch(watch_id)
            or not isinstance(evidence_class, str)
            or evidence_class not in EVIDENCE_CLASSES
            or row.get("change_kind") not in {"added", "removed", "content_changed"}
        ):
            raise ValueError(f"selection tick {label} row is invalid")
        if row["change_kind"] == "removed" and evidence_class in {
            "exact_subject",
            "authority",
        }:
            raise ValueError(f"selection tick {label} cannot remove sticky evidence")
        rows.append({key: str(row[key]) for key in keys})
    if len({row["watch_id"] for row in rows}) != len(rows):
        raise ValueError(f"selection tick {label} has duplicate watch IDs")
    return rows


def _validate_acknowledgement(packet: dict[str, Any]) -> None:
    status = packet["selection_acknowledgement_status"]
    binding = packet["selection_acknowledgement_binding"]
    rebased = packet["baseline_rebased"]
    if status not in ACK_STATUSES:
        raise ValueError("selection acknowledgement status is invalid")
    if status == "not_requested":
        if (
            any(
                value is not None
                for value in (
                    binding,
                    packet["acknowledgement_requested_for_packet_id"],
                    packet["acknowledged_selection_tick_id"],
                )
            )
            or rebased
        ):
            raise ValueError("unrequested selection acknowledgement has state")
        return
    if not isinstance(binding, dict) or set(binding) != ACKNOWLEDGEMENT_KEYS:
        raise ValueError("selection acknowledgement binding schema is invalid")
    trigger = binding.get("trigger_tick_id")
    receipt_id = binding.get("selection_receipt_id")
    receipt_ref = binding.get("selection_receipt_ref")
    receipt_sha = binding.get("selection_receipt_sha256")
    receipt_integrity_sha = binding.get("selection_receipt_integrity_sha256")
    outcome = binding.get("selection_outcome")
    selected_task_id = binding.get("selected_task_id")
    if (
        not isinstance(trigger, str)
        or not PACKET_ID.fullmatch(trigger)
        or not isinstance(binding.get("trigger_tick_sha256"), str)
        or not SHA256.fullmatch(binding["trigger_tick_sha256"])
        or not isinstance(receipt_id, str)
        or not OPAQUE_ID.fullmatch(receipt_id)
        or not isinstance(receipt_sha, str)
        or not SHA256.fullmatch(receipt_sha)
        or not isinstance(receipt_integrity_sha, str)
        or not SHA256.fullmatch(receipt_integrity_sha)
        or packet["acknowledgement_requested_for_packet_id"] != trigger
    ):
        raise ValueError("selection acknowledgement identity is invalid")
    if (
        not isinstance(receipt_ref, str)
        or not receipt_ref
        or len(receipt_ref) > 512
        or "\\" in receipt_ref
        or "\x00" in receipt_ref
    ):
        raise ValueError("selection acknowledgement receipt ref is unsafe")
    pure_ref = PurePosixPath(receipt_ref)
    if (
        pure_ref.is_absolute()
        or pure_ref.as_posix() != receipt_ref
        or any(part in {"", ".", ".."} for part in pure_ref.parts)
    ):
        raise ValueError("selection acknowledgement receipt ref is unsafe")
    if outcome not in SELECTION_OUTCOMES or (
        (outcome == "selected")
        is not (
            isinstance(selected_task_id, str)
            and bool(OPAQUE_ID.fullmatch(selected_task_id))
        )
    ):
        raise ValueError("selection acknowledgement outcome is invalid")
    if outcome != "selected" and selected_task_id is not None:
        raise ValueError("non-selected acknowledgement carries a task ID")
    if status == "accepted":
        if (
            not rebased
            or packet["acknowledged_selection_tick_id"] != trigger
            or packet["status"] != "baseline_recorded"
            or packet["selection_required"] is not False
        ):
            raise ValueError("accepted selection acknowledgement is not rebased")
    elif rebased or packet["acknowledged_selection_tick_id"] is not None:
        raise ValueError("unaccepted selection acknowledgement cannot rebase")
    elif status == "rejected_input_drift" and (
        packet["status"] != "selection_required"
        or packet["selection_required"] is not True
    ):
        raise ValueError("drift-rejected acknowledgement must require selection")
    elif status == "blocked_publication" and packet["status"] not in {
        "recovery_required",
        "drift_blocked",
    }:
        raise ValueError("publication-blocked acknowledgement lacks a blocker")


def _validated_disposition_fields(
    packet: dict[str, Any], predicates: list[str]
) -> tuple[str, bool, list[str]]:
    status = packet["status"]
    required = packet["selection_required"]
    if (
        not isinstance(status, str)
        or status not in STATUSES
        or not isinstance(packet.get("reason"), str)
        or not packet["reason"]
        or required is not (status == "selection_required")
    ):
        raise ValueError("selection tick status and selection_required disagree")
    if packet["agent_fanout_allowed"] is not required:
        raise ValueError("selection tick fanout does not match selection_required")
    if packet["satisfied_wake_predicates"] != (predicates if required else []):
        raise ValueError("selection tick satisfied wake predicates are inconsistent")
    pending = _ids(
        packet["pending_selection_publication_ids"],
        "pending publication IDs",
        max_count=MAX_PENDING_PUBLICATIONS,
    )
    next_actions = {
        "recovery_required": "recover_selection_publication",
        "drift_blocked": "repair_selection_publication_drift",
        "selection_required": "run_derive_selection",
        "baseline_recorded": "preserve_terminal_wait",
        "no_op": "preserve_terminal_wait",
    }
    if packet["next_action"] != next_actions[status]:
        raise ValueError("selection tick next action is inconsistent")
    if (status == "recovery_required") is not bool(pending):
        raise ValueError("selection tick pending publication state is inconsistent")
    if (
        packet["full_cycle_allowed"] is not False
        or packet["not_goal_truth"] is not True
        or packet["not_authority"] is not True
        or packet["mutation_performed"] is not False
        or not isinstance(packet["baseline_rebased"], bool)
        or not isinstance(packet["exact_premise_supplied"], bool)
        or not isinstance(packet["fresh_exact_premise_detected"], bool)
    ):
        raise ValueError("selection tick fixed non-claim fields are invalid")
    return status, required, pending


def validate_selection_tick_v2(packet: Any) -> dict[str, Any]:
    """Validate exact v2 fields and cross-field invariants without external I/O."""

    if not isinstance(packet, dict) or set(packet) != V2_PACKET_KEYS:
        raise ValueError("selection tick v2 requires its exact top-level fields")
    if (
        packet.get("format_version") != 2
        or packet.get("artifact_kind") != "selection_tick"
    ):
        raise ValueError("selection tick v2 schema is invalid")
    premise_contract = packet.get("premise_input_contract")
    if (
        not isinstance(premise_contract, str)
        or premise_contract not in PREMISE_CONTRACTS
    ):
        raise ValueError("selection tick premise contract is invalid")
    watches = _watch_rows(packet["watch_entries"], premise_contract)
    manifest = hashlib.sha256(canonical_bytes(watches)).hexdigest()
    if packet.get("observed_input_manifest_sha256") != manifest:
        raise ValueError("selection tick observed manifest does not match watch rows")
    previous = packet.get("previous_input_manifest_sha256")
    if previous is not None and (
        not isinstance(previous, str) or not SHA256.fullmatch(previous)
    ):
        raise ValueError("selection tick previous manifest is invalid")
    changes = _change_rows(packet["changed_watch_entries"], "changed_watch_entries")
    material = _change_rows(
        packet["material_changed_watch_entries"], "material_changed_watch_entries"
    )
    watch_by_id = {str(row["watch_id"]): row for row in watches}
    for row in changes:
        current = watch_by_id.get(row["watch_id"])
        if row["change_kind"] == "removed":
            if current is not None:
                raise ValueError("removed selection watch still exists in current rows")
        elif current is None or (
            current.get("evidence_class") != row["evidence_class"]
            and not (
                row["evidence_class"] == "task_pack"
                and current.get("evidence_class") == "task_state"
                and current.get("kind") == "workflow_input"
                and str(current.get("path") or "").startswith(
                    ".task/task_pack/"
                )
            )
        ):
            raise ValueError("changed selection watch does not match current rows")
    classes = _ids(
        packet["watched_evidence_classes"],
        "watched evidence classes",
        max_count=MAX_POLICY_IDS,
    )
    if any(item not in EVIDENCE_CLASSES for item in classes):
        raise ValueError("selection tick watched evidence class is unsupported")
    expected_material = material_watch_entries(changes, watches, classes)
    if material != expected_material:
        raise ValueError("selection tick material changes do not match watched classes")
    if (
        not isinstance(packet["changed_evidence_classes"], list)
        or len(packet["changed_evidence_classes"]) > MAX_POLICY_IDS
        or packet["changed_evidence_classes"]
        != sorted({row["evidence_class"] for row in changes})
    ):
        raise ValueError("selection tick changed evidence classes are inconsistent")
    predicates = _ids(
        packet["wake_predicates"], "wake predicates", max_count=MAX_POLICY_IDS
    )
    if not predicates or not classes:
        raise ValueError("selection tick wake predicates and classes cannot be empty")
    _ids(
        packet["satisfied_wake_predicates"],
        "satisfied wake predicates",
        max_count=MAX_POLICY_IDS,
    )
    if (
        packet["wake_evaluation_rule"] != "explicit-premise-or-bound-class-change-v1"
        or packet["wake_predicate_ids_are_policy_labels"] is not True
        or not isinstance(packet["minimum_material_delta"], str)
        or not OPAQUE_ID.fullmatch(packet["minimum_material_delta"])
    ):
        raise ValueError("selection tick wake policy is invalid")
    _status, _required, pending = _validated_disposition_fields(packet, predicates)
    carried = _ids(
        packet["carried_forward_watch_ids"],
        "carried watch IDs",
        max_count=MAX_CARRIED_WATCH_IDS,
    )
    if not set(carried) <= {str(row["watch_id"]) for row in watches}:
        raise ValueError("selection tick carried watch IDs are unknown")
    if set(carried) & {row["watch_id"] for row in changes}:
        raise ValueError("selection tick changed watch cannot be carried forward")
    authority_scope_ids = _ids(
        packet["authority_scope_ids"],
        "authority scope IDs",
        max_count=MAX_AUTHORITY_SCOPES,
    )
    expected_scopes = sorted(
        str(row["authority_scope_id"])
        for row in watches
        if row.get("kind") == "effective_authority"
    )
    if authority_scope_ids != expected_scopes:
        raise ValueError("selection tick authority scope IDs are inconsistent")
    _validate_acknowledgement(packet)
    validate_tick_causality(
        packet,
        watches=watches,
        changes=changes,
        material=material,
        previous_manifest=previous,
        observed_manifest=manifest,
        pending_publications=pending,
        premise_contract=premise_contract,
    )
    body = {key: value for key, value in packet.items() if key != "packet_id"}
    expected_id = (
        "selection-tick-" + hashlib.sha256(canonical_bytes(body)).hexdigest()[:32]
    )
    if packet["packet_id"] != expected_id:
        raise ValueError("selection tick packet ID is invalid")
    return packet


__all__ = (
    "ACKNOWLEDGEMENT_KEYS",
    "V2_PACKET_KEYS",
    "canonical_bytes",
    "validate_selection_tick_v2",
)
