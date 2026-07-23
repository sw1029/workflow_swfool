"""Creation snapshots, authority receipts, and bound receipt validation."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .contracts import (
    AUTHORITY_RECEIPT_SOURCE_KINDS,
    AUTHORITY_RECEIPT_TEMPORALITIES,
    CONTEMPORANEOUS_AUTHORITY_SOURCE_KINDS,
    CREATION_SNAPSHOT_CANONICALIZATION_VERSION,
    INITIAL_SELECTION_RECEIPT_VERSION,
    SHA256_PATTERN,
)
from .ordering import item_order, sorted_items
from .packet_io import non_empty, require_file_digest, write_content_addressed_file
from .storage import (
    _require_within,
    bounded_workspace_file,
    bounded_workspace_path,
    canonical_pack_sha256,
    creation_receipt_dir,
    creation_snapshot_dir,
    json_bytes,
    now_iso,
    pack_dir,
    parse_rfc3339,
    rel_path,
    sha256_bytes,
)

INITIAL_SELECTION_REQUIRED_FIELDS = (
    "pack_ref",
    "pack_creation_snapshot_kind",
    "pack_creation_snapshot_ref",
    "pack_creation_snapshot_sha256",
    "pack_creation_canonical_sha256",
    "pack_creation_canonicalization_version",
    "creation_snapshot_state",
    "initial_item_id",
    "initial_order",
    "task_id",
    "task_snapshot_ref",
    "task_snapshot_sha256",
    "authority_receipt_ref",
    "authority_receipt_sha256",
    "authority_mode",
    "historical_selection_authority_status",
    "selection_reason",
    "created_at",
)


def _forbidden_receipt_key_paths(value: Any, prefix: str = "$") -> list[str]:
    forbidden = {
        "bounded_quote",
        "raw_prompt",
        "prompt_body",
        "quote",
        "quote_body",
        "instruction_text",
        "transcript_body",
        "transcript_path",
        "user_message",
        "source_text",
        "corpus_metadata",
        "credential",
        "token",
        "secret",
    }
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if str(key).lower() in forbidden:
                found.append(path)
            found.extend(_forbidden_receipt_key_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_receipt_key_paths(item, f"{prefix}[{index}]"))
    return found


def _required_sha256(value: Any, label: str) -> str:
    normalized = str(value or "").removeprefix("sha256:").lower()
    if not SHA256_PATTERN.fullmatch(normalized):
        raise SystemExit(f"{label} requires a full lowercase SHA-256 digest.")
    return normalized


def _creation_snapshot_material(
    root: Path, pack_path: Path, data: dict[str, Any]
) -> tuple[dict[str, Any], Path, bytes, Path, bytes]:
    payload = json_bytes(data)
    file_digest = sha256_bytes(payload)
    canonical_digest = canonical_pack_sha256(data)
    pack_id = str(data.get("pack_id") or "")
    snapshot_path = _require_within(
        creation_snapshot_dir(root) / f"{pack_id}-{file_digest[:16]}.json",
        creation_snapshot_dir(root),
        "Creation snapshot path",
    )
    receipt = {
        "schema_version": 1,
        "receipt_kind": "task_pack_creation",
        "canonicalization_version": CREATION_SNAPSHOT_CANONICALIZATION_VERSION,
        "pack_ref": rel_path(root, pack_path),
        "pack_id": pack_id,
        "creation_snapshot_kind": "workspace_file",
        "creation_snapshot_state": "pre_selection",
        "creation_snapshot_ref": rel_path(root, snapshot_path),
        "creation_snapshot_file_sha256": file_digest,
        "creation_snapshot_canonical_sha256": canonical_digest,
        "item_ids": item_order(data),
        "current_item_id": data.get("current_item_id"),
        "created_at": data.get("created_at") or now_iso(),
    }
    receipt_path = _require_within(
        creation_receipt_dir(root) / f"{pack_id}-{file_digest[:16]}.json",
        creation_receipt_dir(root),
        "Creation receipt path",
    )
    receipt_payload = json_bytes(receipt)
    projection = {
        **receipt,
        "creation_receipt_ref": rel_path(root, receipt_path),
        "creation_receipt_sha256": sha256_bytes(receipt_payload),
    }
    return projection, snapshot_path, payload, receipt_path, receipt_payload


def render_creation_snapshot(
    root: Path, pack_path: Path, data: dict[str, Any]
) -> dict[str, Any]:
    """Predict exact creation evidence without touching the filesystem."""

    projection, _snapshot, _payload, _receipt, _receipt_payload = (
        _creation_snapshot_material(root, pack_path, data)
    )
    return projection


def persist_creation_snapshot(
    root: Path, pack_path: Path, data: dict[str, Any]
) -> dict[str, Any]:
    """Persist the exact planned creation body and a durable receipt."""

    projection, snapshot_path, payload, receipt_path, receipt_payload = (
        _creation_snapshot_material(root, pack_path, data)
    )
    write_content_addressed_file(snapshot_path, payload, "Creation snapshot")
    write_content_addressed_file(
        receipt_path, receipt_payload, "Creation receipt"
    )
    return projection


def load_bound_creation_snapshot(
    root: Path,
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], bytes, str, str]:
    kind = str(receipt.get("pack_creation_snapshot_kind") or "workspace_file")
    reference = str(receipt.get("pack_creation_snapshot_ref") or "")
    if kind == "workspace_file":
        path = bounded_workspace_file(root, reference, "pack_creation_snapshot_ref")
        payload = path.read_bytes()
    elif kind == "git_blob":
        commit = str(receipt.get("pack_creation_git_commit") or "").lower()
        git_path = str(receipt.get("pack_creation_git_path") or "")
        if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            raise SystemExit("Git creation snapshot requires a full hexadecimal commit ID.")
        raw_path = Path(git_path)
        if not git_path or raw_path.is_absolute() or ".." in raw_path.parts:
            raise SystemExit("Git creation snapshot path must be workspace-relative and traversal-free.")
        expected_ref = f"git:{commit}:{raw_path.as_posix()}"
        if reference != expected_ref:
            raise SystemExit("Git creation snapshot ref does not match commit and path.")
        process = subprocess.run(
            ["git", "show", f"{commit}:{raw_path.as_posix()}"],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if process.returncode != 0:
            raise SystemExit("Git creation snapshot cannot be resolved from the declared commit.")
        payload = process.stdout
    else:
        raise SystemExit("Creation snapshot kind must be workspace_file or git_blob.")

    file_digest = sha256_bytes(payload)
    declared_file_digest = _required_sha256(
        receipt.get("pack_creation_snapshot_sha256"),
        "pack_creation_snapshot_sha256",
    )
    if file_digest != declared_file_digest:
        raise SystemExit("Creation snapshot file SHA-256 does not match.")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("Creation snapshot is not a UTF-8 JSON object.") from exc
    if not isinstance(data, dict):
        raise SystemExit("Creation snapshot must be a JSON object.")
    if receipt.get("pack_creation_canonicalization_version") != CREATION_SNAPSHOT_CANONICALIZATION_VERSION:
        raise SystemExit("Creation snapshot canonicalization version is unsupported.")
    canonical_digest = canonical_pack_sha256(data)
    if canonical_digest != _required_sha256(
        receipt.get("pack_creation_canonical_sha256"),
        "pack_creation_canonical_sha256",
    ):
        raise SystemExit("Creation snapshot canonical SHA-256 does not match.")
    return data, payload, file_digest, canonical_digest


def load_bound_authority_receipt(
    root: Path,
    reference: Any,
    expected_digest: Any,
    expected_operation: str,
    expected_subject: dict[str, Any],
    selected_at: Any,
) -> tuple[dict[str, Any], str]:
    path = bounded_workspace_file(root, reference, "authority_receipt_ref")
    digest = require_file_digest(path, expected_digest, "Authority receipt")
    try:
        authority = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("Authority receipt is not valid JSON.") from exc
    if not isinstance(authority, dict):
        raise SystemExit("Authority receipt must be a JSON object.")
    if _forbidden_receipt_key_paths(authority):
        raise SystemExit("Authority receipt contains forbidden body-bearing or sensitive keys.")
    if (
        authority.get("schema_version") != 1
        or authority.get("receipt_kind") != "operation_authority"
        or not non_empty(authority.get("receipt_id"))
    ):
        raise SystemExit("Authority receipt schema or kind is invalid.")
    if authority.get("operation") != expected_operation or authority.get("decision") != "allowed":
        raise SystemExit("Authority receipt operation/decision does not authorize this mutation.")
    if authority.get("subject") != expected_subject:
        raise SystemExit("Authority receipt subject does not match pack, snapshot, item, and task identity.")
    basis = authority.get("authority_basis")
    if not isinstance(basis, dict) or basis.get("integrity_status") != "verified":
        raise SystemExit("Authority receipt basis is missing verified integrity.")
    policy = bounded_workspace_file(root, basis.get("policy_ref"), "authority policy ref")
    source = bounded_workspace_file(root, basis.get("source_evidence_ref"), "authority source evidence ref")
    require_file_digest(policy, basis.get("policy_sha256"), "Authority policy")
    require_file_digest(source, basis.get("source_evidence_sha256"), "Authority source evidence")
    source_kind = str(basis.get("source_kind") or "")
    source_id = str(basis.get("source_id") or "").strip()
    if source_kind not in AUTHORITY_RECEIPT_SOURCE_KINDS or not source_id:
        raise SystemExit("Authority receipt requires a supported source_kind and opaque source_id.")
    temporality = str(authority.get("basis_temporality") or "")
    if temporality not in AUTHORITY_RECEIPT_TEMPORALITIES:
        raise SystemExit("Authority receipt temporality is invalid.")
    selected_time = parse_rfc3339(selected_at, "initial selection created_at")
    issued_time = parse_rfc3339(authority.get("issued_at"), "authority issued_at")
    effective_time = parse_rfc3339(authority.get("effective_at"), "authority effective_at")
    if effective_time > issued_time:
        raise SystemExit("Authority receipt effective_at cannot be after issued_at.")
    historical = authority.get("historical_effect") if isinstance(authority.get("historical_effect"), dict) else {}
    if temporality == "current_ratification":
        if source_kind != "explicit_current_user_instruction" or effective_time <= selected_time:
            raise SystemExit("Current ratification requires later explicit-user authority evidence.")
        if historical.get("historical_selection_authority_status") != "unverifiable_before_ratification":
            raise SystemExit("Current ratification must preserve unverified historical authority.")
        if historical.get("historical_authority_verdict") != "partial" or historical.get("retroactive_claim_allowed") is not False:
            raise SystemExit("Current ratification cannot create a historical authority pass.")
    elif temporality == "contemporaneous_selection_authority":
        if source_kind not in CONTEMPORANEOUS_AUTHORITY_SOURCE_KINDS or effective_time > selected_time:
            raise SystemExit("Contemporaneous selection authority requires a supported source effective by selection time.")
        if (
            historical.get("historical_selection_authority_status") != "verified"
            or historical.get("historical_authority_verdict") != "pass"
            or historical.get("retroactive_claim_allowed") is not False
        ):
            raise SystemExit("Contemporaneous selection authority requires a verified historical pass.")
    elif temporality == "retrospective_evidence_assessment":
        if (
            expected_operation != "task_pack.normalize_initial_selection"
            or source_kind != "contemporaneous_authority_record"
            or effective_time > selected_time
        ):
            raise SystemExit("Retrospective assessment requires an immutable contemporaneous authority record.")
        if (
            historical.get("historical_selection_authority_status") != "verified"
            or historical.get("historical_authority_verdict") != "pass"
            or historical.get("retroactive_claim_allowed") is not False
        ):
            raise SystemExit("Retrospective assessment cannot create or overstate historical authority.")
    effects = set(str(item) for item in authority.get("allowed_effects") or [])
    expected_effect = (
        "append_initial_selection_normalization_provenance"
        if expected_operation == "task_pack.normalize_initial_selection"
        else "promote_first_pack_item"
    )
    if effects != {expected_effect}:
        raise SystemExit("Authority receipt effects do not match the bounded operation.")
    return authority, digest


def _validate_initial_task_snapshot(
    root: Path,
    receipt: dict[str, Any],
    *,
    prospective_task_bytes: bytes | None,
    task_digest: str,
) -> None:
    task_snapshot = (
        bounded_workspace_file(
            root, receipt.get("task_snapshot_ref"), "task_snapshot_ref"
        )
        if prospective_task_bytes is None
        else bounded_workspace_path(
            root, receipt.get("task_snapshot_ref"), "task_snapshot_ref"
        )
    )
    _require_within(task_snapshot, pack_dir(root), "Initial task snapshot")
    declared_digest = (
        require_file_digest(
            task_snapshot,
            receipt.get("task_snapshot_sha256"),
            "Initial task snapshot",
        )
        if prospective_task_bytes is None
        else sha256_bytes(prospective_task_bytes)
    )
    if declared_digest != receipt.get("task_snapshot_sha256"):
        raise SystemExit(
            "Initial task snapshot SHA-256 does not match prospective bytes."
        )
    if declared_digest != task_digest:
        raise SystemExit(
            "Initial task snapshot SHA-256 differs from promotion task identity."
        )


def validate_initial_selection_receipt(
    root: Path,
    pack_path: Path,
    current_pack: dict[str, Any],
    receipt: dict[str, Any],
    *,
    task_id: str,
    task_digest: str,
    operation: str,
    require_mutation_binding: bool = True,
    prospective_creation_snapshot: dict[str, Any] | None = None,
    prospective_task_bytes: bytes | None = None,
) -> dict[str, Any]:
    if receipt.get("schema_version") != INITIAL_SELECTION_RECEIPT_VERSION:
        raise SystemExit("Initial selection receipt requires schema_version=1.")
    missing = [
        field
        for field in INITIAL_SELECTION_REQUIRED_FIELDS
        if not non_empty(receipt.get(field))
    ]
    if missing:
        raise SystemExit(f"Initial selection receipt is incomplete: {', '.join(missing)}")
    expected_pack_ref = rel_path(root, pack_path)
    if receipt.get("pack_ref") != expected_pack_ref:
        raise SystemExit("Initial selection receipt references a different canonical pack.")
    if prospective_creation_snapshot is None:
        snapshot, _, snapshot_file_digest, snapshot_canonical_digest = (
            load_bound_creation_snapshot(root, receipt)
        )
    else:
        snapshot = prospective_creation_snapshot
        snapshot_payload = json_bytes(snapshot)
        snapshot_file_digest = sha256_bytes(snapshot_payload)
        snapshot_canonical_digest = canonical_pack_sha256(snapshot)
        if (
            receipt.get("pack_creation_snapshot_kind") != "workspace_file"
            or receipt.get("pack_creation_snapshot_sha256")
            != snapshot_file_digest
            or receipt.get("pack_creation_canonical_sha256")
            != snapshot_canonical_digest
        ):
            raise SystemExit(
                "Prospective creation snapshot differs from the initial selection receipt."
            )
    if snapshot.get("pack_id") != current_pack.get("pack_id"):
        raise SystemExit("Creation snapshot pack ID differs from the current pack.")
    ordered = sorted_items(snapshot)
    if not ordered or ordered[0].get("order") != 1:
        raise SystemExit("Creation snapshot does not contain a canonical first item.")
    first = ordered[0]
    item_id = str(receipt.get("initial_item_id") or "")
    if receipt.get("initial_order") != 1 or str(first.get("item_id") or "") != item_id:
        raise SystemExit("Initial item identity/order does not match the creation snapshot.")
    if str(receipt.get("task_id") or "") != task_id:
        raise SystemExit("Initial selection task ID does not match promotion provenance.")
    snapshot_promotion = first.get("promotion") if isinstance(first.get("promotion"), dict) else {}
    if receipt.get("creation_snapshot_state") == "created_with_initial_selection":
        if snapshot_promotion.get("task_id") != task_id:
            raise SystemExit("Legacy creation snapshot does not identify the selected task.")
    elif receipt.get("creation_snapshot_state") != "pre_selection":
        raise SystemExit("Creation snapshot state is invalid.")
    _validate_initial_task_snapshot(
        root,
        receipt,
        prospective_task_bytes=prospective_task_bytes,
        task_digest=task_digest,
    )

    expected_subject = {
        "pack_ref": expected_pack_ref,
        "pack_creation_snapshot_ref": receipt.get("pack_creation_snapshot_ref"),
        "pack_creation_snapshot_sha256": snapshot_file_digest,
        "initial_item_id": item_id,
        "initial_order": 1,
        "task_id": task_id,
        "task_snapshot_ref": receipt.get("task_snapshot_ref"),
        "task_snapshot_sha256": task_digest,
    }
    authority_operation = (
        "task_pack.normalize_initial_selection"
        if operation == "normalize_initial_selection_provenance"
        else "task_pack.initial_selection"
    )
    authority, authority_digest = load_bound_authority_receipt(
        root,
        receipt.get("authority_receipt_ref"),
        receipt.get("authority_receipt_sha256"),
        authority_operation,
        expected_subject,
        receipt.get("created_at"),
    )
    if receipt.get("authority_mode") != authority.get("basis_temporality"):
        raise SystemExit("Initial selection and authority receipt temporal modes differ.")
    historical = authority.get("historical_effect") or {}
    if receipt.get("historical_selection_authority_status") != historical.get(
        "historical_selection_authority_status"
    ):
        raise SystemExit("Initial selection receipt overstates historical authority status.")
    expected_action = "normalize_initial_selection_provenance" if operation == "normalize_initial_selection_provenance" else "promote"
    if require_mutation_binding:
        matching = [
            row
            for row in current_pack.get("mutation_log", [])
            if isinstance(row, dict)
            and row.get("action") == expected_action
            and row.get("item_id") == item_id
        ]
        if len(matching) != 1:
            raise SystemExit("Initial selection receipt is not bound to one canonical mutation.")
        if expected_action == "promote" and str(matching[0].get("before_pack_sha256") or "") != snapshot_canonical_digest:
            raise SystemExit("Initial promotion mutation is not bound to the creation snapshot.")
        if expected_action == "normalize_initial_selection_provenance" and matching[0].get(
            "authority_receipt_sha256"
        ) != authority_digest:
            raise SystemExit("Initial normalization mutation is not bound to the authority receipt.")
    return {
        **receipt,
        "pack_creation_snapshot_sha256": snapshot_file_digest,
        "pack_creation_canonical_sha256": snapshot_canonical_digest,
        "task_snapshot_sha256": task_digest,
        "authority_receipt_sha256": authority_digest,
        "authority_mode": authority.get("basis_temporality"),
        "historical_selection_authority_status": historical.get("historical_selection_authority_status"),
    }


def pack_paths(root: Path) -> list[Path]:
    directory = _require_within(pack_dir(root), root, "Task pack directory")
    if not directory.is_dir():
        return []
    paths: list[Path] = []
    for candidate in directory.glob("*.json"):
        path = _require_within(candidate, directory, "Task pack path")
        if not path.is_file():
            raise SystemExit(f"Task pack path does not identify a file: {candidate}")
        paths.append(path)
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)
