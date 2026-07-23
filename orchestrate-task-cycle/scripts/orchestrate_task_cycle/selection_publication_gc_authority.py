"""Authority and receipt contracts at selection-GC effect boundaries."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Callable

from .selection_publication_gc_contract import (
    GC_SCHEMA_VERSION,
    MAX_AUTHORITY_PACKET_BYTES,
    receipt_path,
    relative_ref,
)
from .selection_publication_gc_fs import (
    artifact_binding,
    read_json_relative,
)
from .selection_publication_store import _sha256_bytes


def normalize_binding(value: Any, label: str) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"ref", "sha256"}
        or not isinstance(value.get("ref"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256") or ""))
    ):
        raise ValueError(f"{label} must contain exact ref and sha256")
    ref = relative_ref(value["ref"], f"{label}.ref").as_posix()
    return {"ref": ref, "sha256": str(value["sha256"])}


def read_bound_json(
    root: Path, value: Any, label: str
) -> tuple[dict[str, str], dict[str, Any]]:
    binding = normalize_binding(value, label)
    artifact, payload = read_json_relative(
        root,
        binding["ref"],
        label,
        max_bytes=MAX_AUTHORITY_PACKET_BYTES,
    )
    if _sha256_bytes(payload) != binding["sha256"]:
        raise ValueError(f"{label} digest differs")
    return binding, artifact


def expected_subject(
    root: Path,
    *,
    operation: str,
    plan_id: str,
    plan_path: Path,
    plan_sha: str,
) -> dict[str, str]:
    if operation == "apply_selection_publication_retention":
        return {
            "kind": "selection_publication_gc_plan",
            "ref": plan_path.relative_to(root).as_posix(),
            "digest": plan_sha,
            "revision": plan_id,
        }
    if operation == "restore_selection_publication_retention":
        binding = artifact_binding(
            root, receipt_path(root, plan_id).relative_to(root).as_posix()
        )
        return {
            "kind": "selection_publication_gc_receipt",
            "ref": binding["ref"],
            "digest": binding["sha256"],
            "revision": plan_id,
        }
    raise ValueError("selection-publication gc authority operation is unsupported")


def _validate_packet_projection(
    root: Path, packet: dict[str, Any], *, require_current: bool
) -> None:
    findings: list[dict[str, Any]] = []
    try:
        from ._authority_settlement_immutable import (
            read_immutable_packet_lease,
        )
        from .authority_artifacts import validate_authority_artifacts
        from .authority_boundary import project_authority_packet

        projection = project_authority_packet(packet)
        findings.extend(projection.findings)
        if require_current:
            findings.extend(validate_authority_artifacts(packet, root))
        else:
            read_immutable_packet_lease(root, packet, findings)
    except ImportError as exc:
        raise ValueError(
            "selection-publication gc authority validation dependency is unavailable"
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "selection-publication gc authority packet validation failed"
        ) from exc
    if not projection.valid or findings:
        codes = ", ".join(
            str(row.get("code"))
            for row in findings
            if isinstance(row, dict)
        )
        qualifier = "current and valid" if require_current else "valid"
        raise ValueError(
            f"selection-publication gc authority packet is not {qualifier}"
            + (f": {codes}" if codes else "")
        )


def _current_manifest_contract(
    operation: str, subject_kind: str
) -> dict[str, str]:
    manifest_path = Path(__file__).resolve().parents[2] / "authority.operations.json"
    try:
        payload = manifest_path.read_bytes()
        manifest = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "selection-publication gc operation manifest is unreadable"
        ) from exc
    rows = [
        row
        for row in manifest.get("operations", [])
        if isinstance(row, dict)
        and row.get("operation_id") == operation
        and row.get("operation_version") == "1"
    ]
    if (
        len(rows) != 1
        or rows[0].get("authority_applicability") != "required"
        or rows[0].get("authorization_mechanism") != "grant"
        or rows[0].get("subject_kinds") != [subject_kind]
    ):
        raise ValueError(
            "selection-publication gc operation manifest contract differs"
        )
    return {
        "ref": "orchestrate-task-cycle/authority.operations.json",
        "sha256": _sha256_bytes(payload),
    }


def _validate_operation_subject(
    packet: dict[str, Any],
    *,
    operation: str,
    subject: dict[str, str],
    require_current: bool,
) -> None:
    expected = {
        "skill_id": "orchestrate-task-cycle",
        "skill_version": "2.0.0",
        "operation_id": operation,
        "operation_version": "1",
    }
    binding = packet.get("operation_binding")
    current_manifest = (
        _current_manifest_contract(operation, subject["kind"])
        if require_current
        else None
    )
    observed_manifest = (
        {
            "ref": binding.get("manifest_ref"),
            "sha256": binding.get("manifest_sha256"),
        }
        if isinstance(binding, dict)
        else {}
    )
    if (
        not isinstance(binding, dict)
        or any(binding.get(key) != value for key, value in expected.items())
        or binding.get("mutation_class") != "local_mutation"
        or binding.get("manifest_status") != "verified"
        or (require_current and observed_manifest != current_manifest)
        or packet.get("subject") != subject
        or (packet.get("decision_binding") or {}).get("decision") != "allowed"
    ):
        raise ValueError(
            "selection-publication gc authority operation or subject differs"
        )


def _reservation(
    root: Path, packet: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str], int]:
    projection = packet.get("reservation_binding")
    if (
        not isinstance(projection, dict)
        or projection.get("applicability") != "required"
        or projection.get("status") != "reserved"
        or not isinstance(projection.get("state_version"), int)
    ):
        raise ValueError(
            "selection-publication gc requires a reserved authority lease"
        )
    value = {
        "ref": str(projection.get("artifact_ref") or ""),
        "sha256": str(projection.get("artifact_sha256") or ""),
    }
    binding, artifact = read_bound_json(
        root, value, "selection-publication gc authority reservation"
    )
    return artifact, binding, projection["state_version"]


def _validate_precommit(
    root: Path,
    *,
    packet: dict[str, Any],
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    expected_version: int,
    value: Any,
    require_current: bool,
) -> dict[str, str]:
    binding = normalize_binding(
        value, "selection-publication gc pre-commit verification"
    )
    try:
        from manage_agent_authority.execution_results import (
            validate_pre_commit_verification,
        )

        artifact = validate_pre_commit_verification(
            root,
            reservation,
            reservation_binding,
            binding,
            expected_version=expected_version,
            require_current_state=require_current,
        )
    except ImportError as exc:
        raise ValueError(
            "selection-publication gc pre-commit validation dependency is unavailable"
        ) from exc
    except SystemExit as exc:
        raise ValueError(
            "selection-publication gc pre-commit verification is invalid"
        ) from exc
    if (
        artifact.get("stage") != "pre_commit"
        or artifact.get("request_id")
        != (packet.get("decision_binding") or {}).get("request_id")
    ):
        raise ValueError(
            "selection-publication gc pre-commit verification differs"
        )
    return binding


def validate_effect_authority(
    root: Path,
    *,
    operation: str,
    subject: dict[str, str],
    authority_packet: Any,
    pre_commit_verification: Any,
    require_current: bool = True,
) -> dict[str, Any]:
    packet_binding, packet = read_bound_json(
        root, authority_packet, "selection-publication gc authority packet"
    )
    _validate_packet_projection(root, packet, require_current=require_current)
    _validate_operation_subject(
        packet,
        operation=operation,
        subject=subject,
        require_current=require_current,
    )
    reservation, reservation_binding, version = _reservation(root, packet)
    precommit = _validate_precommit(
        root,
        packet=packet,
        reservation=reservation,
        reservation_binding=reservation_binding,
        expected_version=version,
        value=pre_commit_verification,
        require_current=require_current,
    )
    return {
        "authority_packet": packet_binding,
        "pre_commit_verification": precommit,
        "reservation": reservation_binding,
        "reservation_state_version": version,
    }


def receipt_result(
    root: Path,
    receipt: dict[str, Any],
    path: Path,
    *,
    idempotent_replay: bool,
    mutation_performed: bool,
) -> dict[str, Any]:
    return {
        **receipt,
        "owner_result": artifact_binding(
            root, path.relative_to(root).as_posix()
        ),
        "authority_settlement_required": True,
        "idempotent_replay": idempotent_replay,
        "mutation_performed": mutation_performed,
    }


def validate_completed_replay_authority(
    root: Path,
    *,
    receipt: dict[str, Any],
    operation: str,
    subject: dict[str, str],
    authority_packet: Any,
    pre_commit_verification: Any,
    effect_validator: Callable[..., dict[str, dict[str, str]]] | None = None,
) -> None:
    recorded = receipt.get("authority")
    if not isinstance(recorded, dict) or set(recorded) != {
        "authority_packet",
        "effect_lease",
        "pre_commit_verification",
        "reservation",
        "reservation_state_version",
    }:
        raise ValueError(
            "selection-publication gc receipt authority contract is invalid"
        )
    packet = normalize_binding(
        authority_packet, "selection-publication gc authority packet"
    )
    precommit = normalize_binding(
        pre_commit_verification,
        "selection-publication gc pre-commit verification",
    )
    if (
        packet != recorded.get("authority_packet")
        or precommit != recorded.get("pre_commit_verification")
    ):
        raise ValueError(
            "selection-publication gc receipt authority binding differs"
        )
    validator = effect_validator or validate_effect_authority
    validated = validator(
        root,
        operation=operation,
        subject=subject,
        authority_packet=packet,
        pre_commit_verification=precommit,
        require_current=False,
    )
    stable_recorded = {
        key: value for key, value in recorded.items() if key != "effect_lease"
    }
    if validated != stable_recorded:
        raise ValueError(
            "selection-publication gc immutable replay authority differs"
        )
    try:
        from manage_agent_authority.effect_lease import validate_effect_lease

        validate_effect_lease(
            root,
            recorded["effect_lease"],
            operation=operation,
            subject=subject,
            reservation=recorded["reservation"],
            pre_commit_verification=recorded["pre_commit_verification"],
        )
    except (ImportError, SystemExit) as exc:
        raise ValueError(
            "selection-publication gc effect lease is invalid"
        ) from exc


def validate_apply_receipt_contract(
    receipt: dict[str, Any],
    *,
    plan: dict[str, Any],
    plan_path: Path,
    plan_sha: str,
    root: Path,
) -> None:
    expected_fields = {
        "schema_version",
        "result_kind",
        "status",
        "plan",
        "plan_id",
        "authority",
        "archive",
        "removed_count",
        "removed_bytes",
        "restore_supported",
        "model_authored_mechanical_bytes",
    }
    expected_plan = {
        "ref": plan_path.relative_to(root).as_posix(),
        "sha256": plan_sha,
    }
    if (
        set(receipt) != expected_fields
        or receipt.get("schema_version") != GC_SCHEMA_VERSION
        or receipt.get("result_kind") != "selection_publication_gc_receipt"
        or receipt.get("status") != "applied"
        or receipt.get("plan_id") != plan["plan_id"]
        or receipt.get("plan") != expected_plan
        or receipt.get("removed_count") != len(plan["candidates"])
        or receipt.get("removed_bytes")
        != sum(int(row["size_bytes"]) for row in plan["candidates"])
        or receipt.get("restore_supported") is not True
        or receipt.get("model_authored_mechanical_bytes") != 0
    ):
        raise ValueError("selection-publication gc receipt contract is invalid")


def validate_restore_receipt_contract(
    receipt: dict[str, Any],
    *,
    plan_id: str,
    gc_receipt: dict[str, str],
    candidate_count: int,
) -> None:
    expected_fields = {
        "schema_version",
        "result_kind",
        "status",
        "plan_id",
        "gc_receipt",
        "authority",
        "restored_count",
        "model_authored_mechanical_bytes",
    }
    if (
        set(receipt) != expected_fields
        or receipt.get("schema_version") != GC_SCHEMA_VERSION
        or receipt.get("result_kind")
        != "selection_publication_gc_restore_receipt"
        or receipt.get("status") != "restored"
        or receipt.get("plan_id") != plan_id
        or receipt.get("gc_receipt") != gc_receipt
        or receipt.get("restored_count") != candidate_count
        or receipt.get("model_authored_mechanical_bytes") != 0
    ):
        raise ValueError(
            "selection-publication gc restore receipt contract is invalid"
        )


__all__ = (
    "expected_subject",
    "normalize_binding",
    "receipt_result",
    "validate_apply_receipt_contract",
    "validate_completed_replay_authority",
    "validate_effect_authority",
    "validate_restore_receipt_contract",
)
