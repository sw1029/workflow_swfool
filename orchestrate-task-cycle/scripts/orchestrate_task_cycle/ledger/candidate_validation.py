from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path, PurePosixPath
from typing import Any

from ..result_contract.integrity import actual_report_body_divergences
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
from .constants import (
    DURABLE_STATE_MODES,
    FINALIZATION_SCHEMA_VERSION,
    FINAL_CANDIDATE_KIND,
    SENSITIVE_DURABLE_KEYS,
    SENSITIVE_DURABLE_KEY_PARTS,
    SHA256_PATTERN,
    VERDICT_AXES,
    VERDICT_AXIS_STATUSES,
)
from .event_model import truthy_delta
from .operation_contract import (
    validate_no_change_candidate,
    validate_typed_operations_candidate,
)
from .operation_owner_registry import registered_target_owner_id
from .support import canonical_json_bytes, validate_cycle_id, validate_event_id


MAX_LOOPBACK_PACKET_BYTES = 64 * 1024 * 1024


def _exact_integer(value: Any, expected: int) -> bool:
    return type(value) is int and value == expected


def _candidate_expected_revision(candidate: dict[str, Any]) -> int | None:
    if "expected_previous_revision" not in candidate:
        raise ValueError("final candidate requires explicit expected_previous_revision, including null for first publication")
    value = candidate.get("expected_previous_revision")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("expected_previous_revision must be null or a positive integer")
    return value


def _candidate_expected_identifier(candidate: dict[str, Any], field: str) -> str | None:
    if field not in candidate:
        raise ValueError(f"final candidate requires explicit {field}, including null for first publication")
    value = candidate.get(field)
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field} must be null or a non-empty opaque identifier")
    if field == "expected_previous_finalization_token":
        normalized = normalized.lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("expected_previous_finalization_token must be null or a full lowercase SHA-256 digest")
    else:
        validate_event_id(normalized)
    return normalized


def _positive_progress_markers(value: Any, prefix: str = "durable_state_candidate") -> dict[str, list[str]]:
    markers: dict[str, list[str]] = {"semantic": [], "goal": [], "combined": []}
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            path = f"{prefix}.{raw_key}"
            normalized = str(item).strip().lower() if not isinstance(item, (dict, list)) else ""
            positive_boolean = item is True or normalized in {"true", "yes", "1"}
            if key in {"semantic_progress", "authoritative_semantic_progress"} and positive_boolean:
                markers["semantic"].append(path)
            if key == "goal_productive" and positive_boolean:
                markers["goal"].append(path)
            if key == "progress_kind" and normalized == "goal_productive":
                markers["combined"].append(path)
            if key == "progress_verdict" and normalized in {"advanced", "success", "succeeded", "goal_productive"}:
                markers["combined"].append(path)
            nested = _positive_progress_markers(item, path)
            for category, paths in nested.items():
                markers[category].extend(paths)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            nested = _positive_progress_markers(item, f"{prefix}[{index}]")
            for category, paths in nested.items():
                markers[category].extend(paths)
    return markers


def _durable_key_is_sensitive(key: str) -> bool:
    normalized = key.strip().lower()
    return bool(
        normalized in SENSITIVE_DURABLE_KEYS
        or normalized.endswith("_path")
        or normalized.endswith("_paths")
        or normalized.startswith("path_")
        or any(part in normalized for part in SENSITIVE_DURABLE_KEY_PARTS)
    )


def _durable_string_looks_like_path(value: str) -> bool:
    text = value.strip()
    return bool(text.startswith(("/", "./", "../", "~")) or "\\" in text or "/" in text)


def validate_durable_payload_privacy(value: Any, prefix: str) -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            if _durable_key_is_sensitive(key):
                raise ValueError(f"durable state payload contains prohibited source metadata at {prefix}.{key}")
            validate_durable_payload_privacy(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_durable_payload_privacy(child, f"{prefix}[{index}]")
    elif isinstance(value, str) and _durable_string_looks_like_path(value):
        raise ValueError(f"durable state payload contains a path-like string at {prefix}")


def validate_durable_state_candidate(
    durable_state: Any,
    semantic_status: str,
    goal_status: str,
    attempt_identity: str,
) -> dict[str, Any]:
    if not isinstance(durable_state, dict):
        raise ValueError("final candidate requires a durable_state_candidate JSON object")
    durable_state_mode = str(durable_state.get("mode") or "").strip()
    if durable_state_mode not in DURABLE_STATE_MODES:
        raise ValueError("durable_state_candidate mode must be complete_projection or typed_operations")
    if durable_state_mode == "complete_projection":
        validate_no_change_candidate(
            durable_state, attempt_identity=attempt_identity
        )
    else:
        validate_typed_operations_candidate(
            durable_state, attempt_identity=attempt_identity
        )
        for index, operation in enumerate(durable_state["operations"]):
            validate_durable_payload_privacy(
                operation["payload"],
                f"durable_state_candidate.operations[{index}].payload",
            )
    positive_markers = _positive_progress_markers(durable_state)
    if positive_markers["semantic"] and (semantic_status != "pass" or goal_status != "pass"):
        raise ValueError(
            "durable state contains positive semantic progress that contradicts the final artifact semantic verdict or goal readiness verdict"
        )
    if positive_markers["goal"] and (semantic_status != "pass" or goal_status != "pass"):
        raise ValueError(
            "durable state contains positive goal progress that contradicts the final artifact semantic verdict or goal readiness verdict"
        )
    if positive_markers["combined"] and (semantic_status != "pass" or goal_status != "pass"):
        raise ValueError("durable state contains an advanced progress verdict that contradicts final semantic or goal axes")
    return durable_state


def _validate_verdict_axes(normalized: dict[str, Any]) -> None:
    verdict_contract_version = normalized.get("verdict_contract_version")
    if isinstance(verdict_contract_version, bool) or verdict_contract_version != 1:
        raise ValueError("final candidate verdict_contract_version must be 1")
    for axis in VERDICT_AXES:
        value = normalized.get(axis)
        if not isinstance(value, dict):
            raise ValueError(f"final candidate requires object verdict axis {axis}")
        status = str(value.get("status") or value.get("verdict") or "").strip().lower()
        if status not in VERDICT_AXIS_STATUSES:
            raise ValueError(f"final candidate verdict axis {axis} has invalid status")
        evidence = value.get("evidence_ref") or value.get("evidence_refs")
        if status != "not_applicable" and evidence in (None, "", []):
            raise ValueError(f"final candidate verdict axis {axis} requires bounded evidence")
        if evidence not in (None, "", []):
            validate_durable_payload_privacy(evidence, f"final_candidate.{axis}.evidence")
        normalized[axis] = {**value, "status": status}


def _validate_verdict_aliases(normalized: dict[str, Any]) -> None:
    alias_containers = [
        normalized.get("verdict_axes"),
        normalized.get("result"),
        normalized.get("result", {}).get("verdict_axes") if isinstance(normalized.get("result"), dict) else None,
    ]
    for axis in VERDICT_AXES:
        canonical_status = normalized[axis]["status"]
        for container in alias_containers:
            if not isinstance(container, dict) or axis not in container:
                continue
            alias = container[axis]
            alias_status = (
                str(alias.get("status") or alias.get("verdict") or "").strip().lower()
                if isinstance(alias, dict)
                else str(alias or "").strip().lower()
            )
            if alias_status != canonical_status:
                raise ValueError(f"final candidate verdict alias conflicts with canonical axis {axis}")


def _has_body_divergence(normalized: dict[str, Any]) -> bool:
    divergence_paths = (
        ("report_body_divergence",),
        ("actual_artifact_truth", "report_body_divergence"),
        ("quality_review", "report_body_divergence"),
        ("validation", "actual_artifact_truth", "report_body_divergence"),
        ("result", "report_body_divergence"),
        ("result", "actual_artifact_truth", "report_body_divergence"),
        ("result", "quality_review", "report_body_divergence"),
        ("result", "validation", "actual_artifact_truth", "report_body_divergence"),
    )
    for divergence_path in divergence_paths:
        current: Any = normalized
        for path_part in divergence_path:
            if not isinstance(current, dict) or path_part not in current:
                current = None
                break
            current = current[path_part]
        if truthy_delta(current):
            return True
    return bool(actual_report_body_divergences(normalized))


def _reopened_loopback_packet(
    root: Path,
    handoff: dict[str, Any],
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
        if resolved_path.stat().st_size > MAX_LOOPBACK_PACKET_BYTES:
            raise ValueError("loopback finalization packet exceeds the bounded size limit")
        with resolved_path.open("rb") as handle:
            packet_bytes = handle.read(MAX_LOOPBACK_PACKET_BYTES + 1)
        if len(packet_bytes) > MAX_LOOPBACK_PACKET_BYTES:
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


def _validate_loopback_finalization_binding(
    root: Path,
    normalized: dict[str, Any],
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
    packet = _reopened_loopback_packet(root, handoff)
    _validate_reopened_loopback_packet(normalized, gate, packet, handoff)
    conformance = gate.get("consumer_context_conformance")
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


def _normalize_final_candidate(
    root: Path | None,
    cycle_id: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    cycle_id = validate_cycle_id(cycle_id)
    if not isinstance(candidate, dict):
        raise ValueError("final candidate must be a JSON object")
    normalized = dict(candidate)
    schema_version = normalized.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != FINALIZATION_SCHEMA_VERSION:
        raise ValueError("final candidate schema_version must be 1")
    if normalized.get("kind") != FINAL_CANDIDATE_KIND:
        raise ValueError(f"final candidate kind must be {FINAL_CANDIDATE_KIND}")
    if normalized.get("final_candidate") is not True:
        raise ValueError("completion output must explicitly mark final_candidate true")
    if str(normalized.get("cycle_id") or "") != cycle_id:
        raise ValueError("final candidate cycle_id does not match finalization cycle")
    normalized["attempt_id"] = validate_event_id(normalized.get("attempt_id"))
    owner_fields = {
        "attempt_revision", "supersedes_revision", "supersedes_finalization_token",
        "finalization_token", "state_commit_status", "receipt_hash", "authoritative_final",
    }
    supplied_owner_fields = sorted(owner_fields.intersection(normalized))
    if supplied_owner_fields:
        raise ValueError(
            "revision, supersession, receipt, and authoritative verdict fields are assigned only by the finalization owner: "
            + ", ".join(supplied_owner_fields)
        )
    projection_fields = sorted({
        "authoritative_projection", "authoritative_projection_digest",
        "authoritative_projection_id", "validation_axes_digest",
    }.intersection(normalized))
    nested_projection = (
        isinstance(normalized.get("finalization"), dict)
        and isinstance(normalized["finalization"].get("authoritative_projection"), dict)
    ) or (
        isinstance(normalized.get("result"), dict)
        and isinstance(normalized["result"].get("authoritative_projection"), dict)
    )
    if projection_fields or nested_projection:
        raise ValueError("authoritative projection fields are assigned only by the finalization owner")
    normalized["expected_previous_revision"] = _candidate_expected_revision(normalized)
    normalized["expected_previous_attempt_id"] = _candidate_expected_identifier(normalized, "expected_previous_attempt_id")
    normalized["expected_previous_finalization_token"] = _candidate_expected_identifier(
        normalized, "expected_previous_finalization_token"
    )
    _validate_verdict_axes(normalized)
    _validate_verdict_aliases(normalized)
    if _has_body_divergence(normalized):
        truth_status = normalized["artifact_truth_verdict"]["status"]
        semantic_status = normalized["artifact_semantic_verdict"]["status"]
        goal_status = normalized["goal_readiness_verdict"]["status"]
        if "conflicted" not in {truth_status, semantic_status} or semantic_status == "pass" or goal_status == "pass":
            raise ValueError(
                "body/report divergence requires a conflicted artifact axis and blocks favorable semantic or goal publication"
            )
    semantic_status = normalized["artifact_semantic_verdict"]["status"]
    goal_status = normalized["goal_readiness_verdict"]["status"]
    normalized["durable_state_candidate"] = validate_durable_state_candidate(
        normalized.get("durable_state_candidate"),
        semantic_status,
        goal_status,
        normalized["attempt_id"],
    )
    if root is not None:
        _validate_loopback_finalization_binding(root, normalized)
    try:
        canonical_json_bytes(normalized)
    except (TypeError, ValueError) as exc:
        raise ValueError("final candidate must contain only JSON-serializable values") from exc
    return normalized


def normalize_final_candidate(
    cycle_id: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Preserve the exported pure normalizer API used by existing callers."""

    return _normalize_final_candidate(None, cycle_id, candidate)


def normalize_final_candidate_for_root(
    root: Path,
    cycle_id: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Normalize and verify root-bound loopback handoffs for publication."""

    return _normalize_final_candidate(root, cycle_id, candidate)


def authoritative_final_from_axes(axes: dict[str, dict[str, Any]]) -> str:
    statuses = {str(value.get("status") or "") for value in axes.values()}
    if "fail" in statuses:
        return "failure"
    if "conflicted" in statuses or "blocked" in statuses:
        return "blocked"
    if "partial" in statuses:
        return "partial"
    if "not_evaluated" in statuses:
        return "not_evaluated"
    return "success"


def final_candidate_commit_material(candidate: dict[str, Any]) -> dict[str, Any]:
    """Select only decision-bound candidate fields for idempotency and receipts."""
    fields = (
        "schema_version", "kind", "final_candidate", "cycle_id", "attempt_id",
        "expected_previous_revision", "expected_previous_attempt_id",
        "expected_previous_finalization_token", "verdict_contract_version",
        *VERDICT_AXES, "durable_state_candidate",
    )
    material = {field: candidate[field] for field in fields}
    bind_loopback_material = bool(
        isinstance(candidate.get("anti_loop_progress_gate"), dict)
        or isinstance(candidate.get("anti_loop_handoff"), dict)
        or explicit_v2_floor_declared(candidate.get("decision_artifact_ref"))
    )
    for field in (
        "decision_artifact_ref",
        "anti_loop_progress_gate",
        "anti_loop_handoff",
    ):
        if bind_loopback_material and field in candidate:
            material[field] = candidate[field]
    return material
