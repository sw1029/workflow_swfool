from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path, PurePosixPath
from typing import Any

from ..result_contract.consumer_receipt_contract import (
    consumer_receipt_binding_sha256,
    validate_consumer_receipt_binding,
)
from ..result_contract.decision_identity_dimensions import (
    expected_dimension_echo,
    expected_subject_echo,
    explicit_identity_object,
    explicit_v2_floor_declared,
    parse_decision_identity,
)
from .constants import SHA256_PATTERN
from .operation_owner_registry import registered_target_owner_id


def _exact_integer(value: Any, expected: int) -> bool:
    return type(value) is int and value == expected


def _reopened_loopback_packet(
    root: Path,
    handoff: dict[str, Any],
    *,
    max_packet_bytes: int,
) -> dict[str, Any]:
    raw_ref = handoff.get("packet_ref")
    expected_sha = str(handoff.get("packet_sha256") or "").strip().lower()
    if (
        not isinstance(raw_ref, str)
        or not raw_ref.strip()
        or raw_ref != raw_ref.strip()
        or any(character.isspace() for character in raw_ref)
        or "\\" in raw_ref
        or "\x00" in raw_ref
        or not SHA256_PATTERN.fullmatch(expected_sha)
    ):
        raise ValueError("loopback finalization requires a valid packet ref and digest")
    relative_ref = PurePosixPath(raw_ref)
    if (
        relative_ref.is_absolute()
        or raw_ref != relative_ref.as_posix()
        or any(component in {"", ".", ".."} for component in relative_ref.parts)
    ):
        raise ValueError("loopback finalization packet ref is not a safe local file")
    resolved_root = root.expanduser().resolve(strict=True)
    lexical_path = resolved_root
    for index, component in enumerate(relative_ref.parts):
        lexical_path = lexical_path / component
        try:
            component_stat = lexical_path.lstat()
        except OSError as exc:
            raise ValueError(
                "loopback finalization packet ref is not a safe local file"
            ) from exc
        if stat.S_ISLNK(component_stat.st_mode) or (
            index < len(relative_ref.parts) - 1
            and not stat.S_ISDIR(component_stat.st_mode)
        ):
            raise ValueError("loopback finalization packet ref is not a safe local file")
    try:
        resolved_path = lexical_path.resolve(strict=True)
        resolved_path.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ValueError("loopback finalization packet ref is not a safe local file") from exc
    if not stat.S_ISREG(resolved_path.lstat().st_mode):
        raise ValueError("loopback finalization packet ref is not a regular non-symlink file")
    try:
        if resolved_path.stat().st_size > max_packet_bytes:
            raise ValueError("loopback finalization packet exceeds the bounded size limit")
        with resolved_path.open("rb") as handle:
            packet_bytes = handle.read(max_packet_bytes + 1)
        if len(packet_bytes) > max_packet_bytes:
            raise ValueError("loopback finalization packet exceeds the bounded size limit")
        packet = json.loads(packet_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("loopback finalization packet is unreadable or malformed") from exc
    if hashlib.sha256(packet_bytes).hexdigest() != expected_sha or not isinstance(
        packet, dict
    ):
        raise ValueError("loopback finalization packet digest or body is invalid")
    return packet


def _loopback_owned_durable_state(durable_state: dict[str, Any]) -> bool:
    if durable_state.get("mode") == "typed_operations":
        target_refs = [
            operation.get("target_ref")
            for operation in durable_state.get("operations") or []
            if isinstance(operation, dict)
        ]
    else:
        evidence = durable_state.get("no_change_evidence")
        observations = (
            evidence.get("target_observations")
            if isinstance(evidence, dict)
            else []
        )
        target_refs = [
            observation.get("target_ref")
            for observation in observations or []
            if isinstance(observation, dict)
        ]
    return any(
        isinstance(target_ref, str)
        and registered_target_owner_id(target_ref) == "audit-cycle-loopback"
        for target_ref in target_refs
    )


def _loopback_binding_required(normalized: dict[str, Any]) -> bool:
    return bool(
        normalized.get("anti_loop_handoff") is not None
        or explicit_v2_floor_declared(normalized.get("decision_artifact_ref"))
        or _loopback_owned_durable_state(normalized["durable_state_candidate"])
    )


def _consumer_context_conformance_pass(
    packet: dict[str, Any],
) -> bool:
    conformance = packet.get("consumer_context_conformance")
    if not isinstance(conformance, dict):
        return False
    status = str(conformance.get("status") or "").strip().lower()
    required = conformance.get("required_consumer_ids")
    missing = conformance.get("missing_consumer_context_ids")
    rows = conformance.get("rows")
    contracts = conformance.get("consumer_contracts", [])
    if not isinstance(required, list) or any(
        not isinstance(item, str) or not item.strip() for item in required
    ):
        return False
    if len(required) != len(set(required)) or not isinstance(missing, list):
        return False
    if status == "not_applicable":
        return not required and not missing
    if (
        status != "pass"
        or not required
        or missing
        or not isinstance(rows, list)
        or not isinstance(contracts, list)
    ):
        return False
    by_id: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            return False
        consumer_id = str(row.get("consumer_context_id") or "").strip()
        if consumer_id:
            by_id.setdefault(consumer_id, []).append(row)
    if set(by_id) != set(required) or any(len(items) != 1 for items in by_id.values()):
        return False

    contracts_by_id: dict[str, list[dict[str, Any]]] = {}
    for contract in contracts:
        if not isinstance(contract, dict):
            return False
        consumer_id = str(contract.get("consumer_id") or "").strip()
        if not consumer_id:
            return False
        contracts_by_id.setdefault(consumer_id, []).append(contract)
    if not set(contracts_by_id).issubset(set(required)) or any(
        len(items) != 1 for items in contracts_by_id.values()
    ):
        return False

    decision_ref = packet.get("decision_artifact_ref")
    identity = parse_decision_identity(explicit_identity_object(decision_ref) or decision_ref)
    expected_echo = (
        {
            **expected_subject_echo(decision_ref),
            "dimension_values": expected_dimension_echo(decision_ref),
        }
        if identity.explicit and not identity.issues
        else None
    )
    for row in (items[0] for items in by_id.values()):
        consumer_id = str(row.get("consumer_context_id") or "").strip()
        consumer_contracts = contracts_by_id.get(consumer_id, [])
        contract = consumer_contracts[0] if consumer_contracts else {}
        explicit_consumer = bool(
            identity.explicit or row.get("consumer_contract_version") == 2
        )
        if explicit_consumer and (
            len(consumer_contracts) != 1
            or contract.get("contract_conflicted") is not False
            or any(
                not isinstance(contract.get(field), str)
                or not str(contract.get(field)).strip()
                for field in ("task_id", "hook_id")
            )
            or any(
                not SHA256_PATTERN.fullmatch(
                    str(contract.get(field) or "").strip().lower()
                )
                for field in (
                    "adapter_revision_sha256",
                    "consumer_revision_sha256",
                )
            )
            or any(
                not isinstance(contract.get(field), list)
                for field in ("required_hook_ids", "required_gate_ids")
            )
        ):
            return False
        binding = validate_consumer_receipt_binding(
            row,
            expected_task_id=contract.get("task_id"),
            expected_adapter_revision_sha256=contract.get(
                "adapter_revision_sha256"
            ),
            expected_hook_id=contract.get("hook_id"),
            expected_consumer_revision_sha256=contract.get(
                "consumer_revision_sha256"
            ),
            expected_required_hook_ids=contract.get("required_hook_ids"),
            expected_required_gate_ids=contract.get("required_gate_ids"),
        )
        if (
            row.get("status") != "pass"
            or row.get("coverage_status") not in {"legacy", "conformant"}
            or row.get("coverage_mismatched_fields") not in (None, [])
            or binding["status"] not in {"legacy", "conformant"}
            or binding["mismatched_fields"]
            or row.get("cycle_id") != packet.get("cycle_id")
            or row.get("attempt_identity") != packet.get("attempt_identity")
            or row.get("adapter_loaded") is not True
            or row.get("hook_resolved") is not True
            or row.get("required_hook_callable") is not True
            or row.get("hook_signature_compatible") is not True
            or row.get("invocation_completed") is not True
            or row.get("return_contract_valid") is not True
            or row.get("artifact_identity_echo_valid") is not True
            or row.get("value_consumed_by_decision") is not True
            or str(row.get("evidence_provenance") or "").strip().lower()
            not in {"independently_verified", "self_grounded"}
            or not str(row.get("probe_evidence_ref") or "").strip()
            or not SHA256_PATTERN.fullmatch(
                str(row.get("probe_evidence_sha256") or "").strip().lower()
            )
            or str(row.get("probe_evidence_sha256") or "").strip().lower()
            != consumer_receipt_binding_sha256(row)
        ):
            return False
        if identity.explicit and (
            row.get("consumer_contract_version") != 2
            or row.get("coverage_status") != "conformant"
            or row.get("decision_identity_kind") != "explicit_v2"
            or row.get("decision_identity_echo") != expected_echo
        ):
            return False
    return True


def _validate_reopened_loopback_packet(
    normalized: dict[str, Any],
    gate: dict[str, Any],
    packet: dict[str, Any],
    handoff: dict[str, Any],
) -> None:
    gate_packet = {
        key: value for key, value in gate.items() if key != "anti_loop_handoff"
    }
    if packet != gate_packet:
        raise ValueError(
            "finalization candidate does not exactly preserve the reopened anti-loop producer packet"
        )
    if (
        packet.get("schema_version") != "anti-loop-progress-gate-v1"
        or not _exact_integer(packet.get("handoff_contract_version"), 1)
        or not _exact_integer(packet.get("decision_contract_version"), 1)
        or packet.get("step") != "loopback_audit"
        or packet.get("cycle_id") != normalized["cycle_id"]
        or not _exact_integer(packet.get("attempt_identity_version"), 2)
        or packet.get("attempt_identity") != normalized["attempt_id"]
        or packet.get("finalization_required") is not True
        or packet.get("finalization_state") != "candidate"
        or packet.get("authoritative_consumption_allowed") is not False
    ):
        raise ValueError(
            "reopened anti-loop producer packet does not satisfy its finalization contract"
        )
    packet_ref = packet.get("decision_artifact_ref")
    if explicit_v2_floor_declared(packet_ref):
        outer_ref = normalized.get("decision_artifact_ref")
        packet_identity = parse_decision_identity(
            explicit_identity_object(packet_ref) or packet_ref
        )
        outer_identity = parse_decision_identity(
            explicit_identity_object(outer_ref) or outer_ref
        )
        if not (
            packet_identity.explicit
            and outer_identity.explicit
            and not packet_identity.issues
            and not outer_identity.issues
            and packet_identity.subject_values == outer_identity.subject_values
            and packet_identity.dimension_statuses
            == outer_identity.dimension_statuses
            and packet_identity.dimension_values == outer_identity.dimension_values
        ):
            raise ValueError(
                "finalization did not consume the exact explicit-v2 producer decision identity"
            )
    mutation = normalized["durable_state_candidate"]
    mutation_sha = str(mutation.get("candidate_sha256") or "").strip().lower()
    compatibility_rows = [
        row
        for row in packet.get("gate_compatibility_results") or []
        if isinstance(row, dict)
    ]
    compatible_gate_ids = sorted(
        str(row.get("gate_id"))
        for row in compatibility_rows
        if row.get("gate_id")
        and row.get("gate_compatibility_status") == "compatible"
    )
    incompatible_gate_ids = sorted(
        str(row.get("gate_id"))
        for row in compatibility_rows
        if row.get("gate_id")
        and row.get("gate_compatibility_status") != "compatible"
    )
    if (
        packet.get("durable_mutation_candidate") != mutation
        or not _exact_integer(handoff.get("handoff_contract_version"), 1)
        or handoff.get("applicability") != "required"
        or handoff.get("finalization_required") is not True
        or handoff.get("authoritative_consumption_allowed") is not False
        or handoff.get("durable_mutation_candidate_sha256") != mutation_sha
        or handoff.get("artifact_id") != packet.get("artifact_id")
        or handoff.get("artifact_sha256") != packet.get("artifact_sha256")
        or handoff.get("artifact_family") != packet.get("artifact_family")
        or handoff.get("blocker_signature") != packet.get("blocker_signature")
        or handoff.get("progress_verdict") != packet.get("progress_verdict")
        or handoff.get("hard_stop") is not (
            packet.get("hard_stop_required") is True
        )
        or handoff.get("terminal_state") != packet.get("terminal_state")
        or handoff.get("allowed_next_action_classes")
        != packet.get("allowed_next_action_classes")
        or handoff.get("compatible_gate_ids") != compatible_gate_ids
        or handoff.get("incompatible_gate_ids") != incompatible_gate_ids
    ):
        raise ValueError(
            "finalization candidate does not match the reopened anti-loop producer packet and handoff"
        )


def validate_loopback_finalization_binding(
    root: Path,
    normalized: dict[str, Any],
    *,
    max_packet_bytes: int,
) -> None:
    gate = normalized.get("anti_loop_progress_gate")
    if gate is None:
        if _loopback_binding_required(normalized):
            raise ValueError(
                "a required, explicit-v2, or loopback-owned finalization cannot omit anti_loop_progress_gate"
            )
        return
    if not isinstance(gate, dict):
        raise ValueError("anti_loop_progress_gate must be an object when supplied")
    if gate.get("finalization_required") is not True:
        raise ValueError(
            "a supplied anti_loop_progress_gate cannot lower finalization_required"
        )
    if gate.get("authoritative_consumption_allowed") is not False:
        raise ValueError(
            "a prepared anti-loop gate cannot grant authoritative consumption"
        )
    attempt_identity = str(gate.get("attempt_identity") or "").strip()
    if attempt_identity != normalized["attempt_id"]:
        raise ValueError(
            "loopback typed mutation and finalizer must consume the same attempt identity"
        )
    mutation = gate.get("durable_mutation_candidate")
    if not isinstance(mutation, dict):
        raise ValueError(
            "a finalization-required loopback gate lacks its prepared durable mutation candidate"
        )
    if normalized["durable_state_candidate"] != mutation:
        raise ValueError(
            "finalization must consume the exact prepared loopback mutation; a separately authored no-change candidate is not equivalent"
        )
    outer_handoff = normalized.get("anti_loop_handoff")
    nested_handoff = gate.get("anti_loop_handoff")
    if (
        isinstance(outer_handoff, dict)
        and isinstance(nested_handoff, dict)
        and outer_handoff != nested_handoff
    ):
        raise ValueError("loopback finalization handoff aliases conflict")
    handoff = outer_handoff if isinstance(outer_handoff, dict) else nested_handoff
    if not isinstance(handoff, dict):
        raise ValueError("finalization-required loopback gate lacks its hash-bound handoff")
    packet = _reopened_loopback_packet(
        root,
        handoff,
        max_packet_bytes=max_packet_bytes,
    )
    _validate_reopened_loopback_packet(normalized, gate, packet, handoff)
    decision_ref = gate.get("decision_artifact_ref")
    identity_status = (
        str(decision_ref.get("identity_status") or "").strip().lower()
        if isinstance(decision_ref, dict)
        else ""
    )
    identity = parse_decision_identity(explicit_identity_object(decision_ref) or decision_ref)
    identity_valid = bool(
        identity_status == "verified"
        and packet.get("scope_verified") is True
        and (
            not explicit_v2_floor_declared(decision_ref)
            or (identity.explicit and not identity.issues)
        )
    )
    conformance_valid = _consumer_context_conformance_pass(packet)
    if not conformance_valid or not identity_valid:
        if (
            normalized["artifact_semantic_verdict"]["status"] == "pass"
            or normalized["goal_readiness_verdict"]["status"] == "pass"
        ):
            raise ValueError(
                "consumer not_evaluated or identity downgrade blocks favorable semantic and goal finalization"
            )
