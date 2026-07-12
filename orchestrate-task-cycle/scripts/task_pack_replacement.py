#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable


REPLACEMENT_TRANSACTION_VERSION = 1
TRANSACTION_ID_PATTERN = re.compile(r"^replace-([0-9a-f]{64})-([0-9a-f]{64})$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _target_projection(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "role": target["role"],
            "target_ref": target["target_ref"],
            "before_sha256": target.get("before_sha256"),
            "after_sha256": target["after_sha256"],
        }
        for target in targets
    ]


def _target_payload(target: dict[str, Any]) -> bytes:
    try:
        payload = base64.b64decode(str(target.get("after_payload_b64") or ""), validate=True)
    except ValueError as exc:
        raise SystemExit("Replacement prepare target payload is invalid base64.") from exc
    if sha256_bytes(payload) != target.get("after_sha256"):
        raise SystemExit("Replacement prepare target payload digest is inconsistent.")
    return payload


def _historical_postcondition(prepare: dict[str, Any]) -> dict[str, Any]:
    metadata = prepare.get("metadata") if isinstance(prepare.get("metadata"), dict) else {}
    targets = {
        str(target.get("role")): target
        for target in prepare.get("targets", [])
        if isinstance(target, dict)
    }
    try:
        predecessor = json.loads(_target_payload(targets["predecessor_pack"]).decode("utf-8"))
        successor = json.loads(_target_payload(targets["successor_pack"]).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("Replacement prepare pack targets are not valid UTF-8 JSON objects.") from exc
    if not isinstance(predecessor, dict) or not isinstance(successor, dict):
        raise SystemExit("Replacement prepare pack targets must contain JSON objects.")
    creation = metadata.get("creation_snapshot") if isinstance(metadata.get("creation_snapshot"), dict) else {}
    return {
        "active_pack_count": 1,
        "active_pack_refs": [metadata.get("successor_pack_ref")],
        "predecessor_status": predecessor.get("status"),
        "successor_status": successor.get("status"),
        "creation_snapshot_ref": creation.get("creation_snapshot_ref"),
        "creation_snapshot_sha256": creation.get("creation_snapshot_file_sha256"),
        "creation_receipt_ref": creation.get("creation_receipt_ref"),
        "creation_receipt_sha256": creation.get("creation_receipt_sha256"),
        "creation_receipt_kind": creation.get("receipt_kind"),
    }


def _binding_sha256(metadata: dict[str, Any], targets: list[dict[str, Any]]) -> str:
    binding = {
        "schema_version": REPLACEMENT_TRANSACTION_VERSION,
        "metadata": metadata,
        "targets": _target_projection(targets),
    }
    return sha256_bytes(json_bytes(binding))


def transaction_id_for_encoded_targets(metadata: dict[str, Any], targets: list[dict[str, Any]]) -> str:
    plan_fingerprint = str(metadata.get("plan_fingerprint") or "")
    if not SHA256_PATTERN.fullmatch(plan_fingerprint):
        raise SystemExit("Replacement transaction requires a plan fingerprint.")
    return f"replace-{plan_fingerprint}-{_binding_sha256(metadata, targets)}"


def transaction_id_for_targets(metadata: dict[str, Any], targets: list[dict[str, Any]]) -> str:
    encoded: list[dict[str, Any]] = []
    for target in targets:
        payload = target.get("after_bytes")
        if not isinstance(payload, bytes):
            raise SystemExit("Replacement target after_bytes must be bytes.")
        encoded.append(
            {
                "role": str(target.get("role") or ""),
                "target_ref": str(target.get("target_ref") or ""),
                "before_sha256": target.get("before_sha256"),
                "after_sha256": sha256_bytes(payload),
            }
        )
    return transaction_id_for_encoded_targets(metadata, encoded)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _write_once(path: Path, payload: bytes, label: str) -> str:
    digest = sha256_bytes(payload)
    if path.exists():
        if not path.is_file() or sha256_file(path) != digest:
            raise SystemExit(f"{label} conflicts with existing immutable transaction evidence.")
        return digest
    atomic_write_bytes(path, payload)
    if sha256_file(path) != digest:
        raise SystemExit(f"{label} failed post-write SHA-256 verification.")
    return digest


def _pack_root(root: Path) -> Path:
    return root.resolve() / ".task" / "task_pack"


def _transaction_root(root: Path) -> Path:
    return _pack_root(root) / "replacement_transactions"


def _receipt_root(root: Path) -> Path:
    return _pack_root(root) / "replacement_receipts"


def _bounded_pack_target(root: Path, reference: str) -> Path:
    raw = Path(str(reference or "").strip())
    if not str(reference or "").strip() or raw.is_absolute():
        raise SystemExit("Replacement target must be a non-empty workspace-relative path.")
    path = (root.resolve() / raw).resolve(strict=False)
    boundary = _pack_root(root).resolve(strict=False)
    try:
        path.relative_to(boundary)
    except ValueError as exc:
        raise SystemExit("Replacement target must remain under .task/task_pack, including through symlinks.") from exc
    return path


def _validate_helper_owned_evidence(root: Path, metadata: dict[str, Any]) -> None:
    creation = metadata.get("creation_snapshot")
    if not isinstance(creation, dict):
        raise SystemExit("Replacement prepare journal is missing creation evidence metadata.")
    for ref_key, digest_key, label in (
        ("creation_snapshot_ref", "creation_snapshot_file_sha256", "creation snapshot"),
        ("creation_receipt_ref", "creation_receipt_sha256", "creation receipt"),
    ):
        reference = str(creation.get(ref_key) or "")
        digest = str(creation.get(digest_key) or "")
        if not SHA256_PATTERN.fullmatch(digest):
            raise SystemExit(f"Replacement {label} digest is invalid.")
        path = _bounded_pack_target(root, reference)
        if sha256_file(path) != digest:
            raise SystemExit(f"Replacement {label} is missing or no longer matches its digest.")


def _validate_plan_snapshot(root: Path, metadata: dict[str, Any]) -> None:
    plan_snapshot_ref = str(metadata.get("plan_snapshot_ref") or "")
    plan_snapshot_sha256 = str(metadata.get("plan_snapshot_sha256") or "")
    if plan_snapshot_sha256 != metadata.get("plan_fingerprint"):
        raise SystemExit("Replacement plan snapshot digest is inconsistent with the plan fingerprint.")
    plan_snapshot_path = _bounded_pack_target(root, plan_snapshot_ref)
    if plan_snapshot_path.name != f"{plan_snapshot_sha256}.json":
        raise SystemExit("Replacement plan snapshot path is not content-addressed by the plan fingerprint.")
    if sha256_file(plan_snapshot_path) != plan_snapshot_sha256:
        raise SystemExit("Replacement plan snapshot is missing or no longer matches the plan fingerprint.")


def prepare_path(root: Path, transaction_id: str) -> Path:
    if not TRANSACTION_ID_PATTERN.fullmatch(transaction_id):
        raise SystemExit("Replacement transaction id is invalid.")
    return _transaction_root(root) / transaction_id / "prepare.json"


def completion_path(root: Path, transaction_id: str) -> Path:
    if not TRANSACTION_ID_PATTERN.fullmatch(transaction_id):
        raise SystemExit("Replacement transaction id is invalid.")
    return _receipt_root(root) / f"{transaction_id}.json"


def pending_transaction_ids(root: Path) -> list[str]:
    directory = _transaction_root(root)
    if not directory.is_dir():
        return []
    pending: list[str] = []
    for child in sorted(directory.iterdir()):
        if not (
            child.is_dir()
            and TRANSACTION_ID_PATTERN.fullmatch(child.name)
            and (child / "prepare.json").is_file()
        ):
            continue
        receipt = completion_path(root, child.name)
        if not receipt.is_file():
            pending.append(child.name)
            continue
        try:
            validate_completed_transaction(root, child.name, require_current_targets=False)
        except SystemExit:
            pending.append(child.name)
    return pending


def pending_transaction_ids_for_plan(root: Path, plan_fingerprint: str) -> list[str]:
    if not SHA256_PATTERN.fullmatch(plan_fingerprint):
        raise SystemExit("Replacement plan fingerprint is invalid.")
    prefix = f"replace-{plan_fingerprint}-"
    return [transaction_id for transaction_id in pending_transaction_ids(root) if transaction_id.startswith(prefix)]


def completed_transaction_ids_for_plan(root: Path, plan_fingerprint: str) -> list[str]:
    if not SHA256_PATTERN.fullmatch(plan_fingerprint):
        raise SystemExit("Replacement plan fingerprint is invalid.")
    directory = _receipt_root(root)
    if not directory.is_dir():
        return []
    prefix = f"replace-{plan_fingerprint}-"
    transaction_ids = [path.stem for path in sorted(directory.glob(f"{prefix}*.json")) if path.is_file()]
    for transaction_id in transaction_ids:
        validate_completed_transaction(root, transaction_id)
    return transaction_ids


def _validated_prepare(root: Path, transaction_id: str) -> tuple[dict[str, Any], Path, str]:
    path = prepare_path(root, transaction_id)
    if not path.is_file():
        raise SystemExit(f"Replacement prepare journal is missing: {path}")
    try:
        prepare = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Replacement prepare journal is unreadable.") from exc
    if not isinstance(prepare, dict):
        raise SystemExit("Replacement prepare journal must be a JSON object.")
    if prepare.get("schema_version") != REPLACEMENT_TRANSACTION_VERSION:
        raise SystemExit("Replacement prepare journal schema version is unsupported.")
    if prepare.get("receipt_kind") != "task_pack_replacement_prepare":
        raise SystemExit("Replacement prepare journal kind is invalid.")
    if prepare.get("transaction_id") != transaction_id:
        raise SystemExit("Replacement prepare journal transaction id is inconsistent.")
    targets = prepare.get("targets")
    if not isinstance(targets, list) or len(targets) < 2:
        raise SystemExit("Replacement prepare journal requires at least predecessor and successor targets.")
    metadata = prepare.get("metadata")
    if not isinstance(metadata, dict) or not SHA256_PATTERN.fullmatch(str(metadata.get("plan_fingerprint") or "")):
        raise SystemExit("Replacement prepare journal requires a plan fingerprint.")
    roles: set[str] = set()
    references: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise SystemExit("Replacement prepare target must be an object.")
        role = str(target.get("role") or "")
        reference = str(target.get("target_ref") or "")
        after_digest = str(target.get("after_sha256") or "")
        before_digest = target.get("before_sha256")
        if not role or role in roles or not reference or reference in references:
            raise SystemExit("Replacement prepare target roles and paths must be unique.")
        if not SHA256_PATTERN.fullmatch(after_digest):
            raise SystemExit("Replacement prepare target after digest is invalid.")
        if before_digest is not None and not SHA256_PATTERN.fullmatch(str(before_digest)):
            raise SystemExit("Replacement prepare target before digest is invalid.")
        _bounded_pack_target(root, reference)
        _target_payload(target)
        roles.add(role)
        references.add(reference)
    if not {"predecessor_pack", "successor_pack"}.issubset(roles):
        raise SystemExit("Replacement prepare journal is missing a predecessor or successor pack target.")
    role_targets = {str(target["role"]): str(target["target_ref"]) for target in targets}
    if metadata.get("predecessor_pack_ref") != role_targets["predecessor_pack"]:
        raise SystemExit("Replacement prepare predecessor metadata is inconsistent.")
    if metadata.get("successor_pack_ref") != role_targets["successor_pack"]:
        raise SystemExit("Replacement prepare successor metadata is inconsistent.")
    match = TRANSACTION_ID_PATTERN.fullmatch(transaction_id)
    if match is None or match.group(1) != metadata.get("plan_fingerprint"):
        raise SystemExit("Replacement transaction id is not bound to the plan fingerprint.")
    if match.group(2) != _binding_sha256(metadata, targets):
        raise SystemExit("Replacement prepare target binding does not match its transaction id.")
    _validate_plan_snapshot(root, metadata)
    _validate_helper_owned_evidence(root, metadata)
    return prepare, path, str(sha256_file(path))


def load_prepare(root: Path, transaction_id: str) -> tuple[dict[str, Any], Path, str]:
    return _validated_prepare(root, transaction_id)


def prepare_transaction(
    root: Path,
    *,
    targets: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    encoded_targets: list[dict[str, Any]] = []
    roles: set[str] = set()
    references: set[str] = set()
    for target in targets:
        payload = target.get("after_bytes")
        if not isinstance(payload, bytes):
            raise SystemExit("Replacement target after_bytes must be bytes.")
        role = str(target.get("role") or "")
        reference = str(target.get("target_ref") or "")
        _bounded_pack_target(root, reference)
        if not role or role in roles or reference in references:
            raise SystemExit("Replacement target roles and paths must be non-empty and unique.")
        before_digest = target.get("before_sha256")
        if before_digest is not None and not SHA256_PATTERN.fullmatch(str(before_digest)):
            raise SystemExit("Replacement target before digest is invalid.")
        encoded_targets.append(
            {
                "role": role,
                "target_ref": reference,
                "before_sha256": before_digest,
                "after_sha256": sha256_bytes(payload),
                "after_payload_b64": base64.b64encode(payload).decode("ascii"),
            }
        )
        roles.add(role)
        references.add(reference)
    if not {"predecessor_pack", "successor_pack"}.issubset(roles):
        raise SystemExit("Replacement transaction requires predecessor and successor pack targets.")
    if not isinstance(metadata, dict) or not SHA256_PATTERN.fullmatch(str(metadata.get("plan_fingerprint") or "")):
        raise SystemExit("Replacement transaction requires a plan fingerprint.")
    role_targets = {str(target["role"]): str(target["target_ref"]) for target in encoded_targets}
    if metadata.get("predecessor_pack_ref") != role_targets["predecessor_pack"]:
        raise SystemExit("Replacement predecessor metadata does not match its target.")
    if metadata.get("successor_pack_ref") != role_targets["successor_pack"]:
        raise SystemExit("Replacement successor metadata does not match its target.")
    _validate_plan_snapshot(root, metadata)
    _validate_helper_owned_evidence(root, metadata)
    transaction_id = transaction_id_for_encoded_targets(metadata, encoded_targets)
    prepare = {
        "schema_version": REPLACEMENT_TRANSACTION_VERSION,
        "receipt_kind": "task_pack_replacement_prepare",
        "transaction_id": transaction_id,
        "metadata": metadata,
        "targets": encoded_targets,
    }
    path = prepare_path(root, transaction_id)
    digest = _write_once(path, json_bytes(prepare), "Replacement prepare journal")
    validated, _path, _digest = _validated_prepare(root, transaction_id)
    return {
        "transaction_id": transaction_id,
        "prepare": validated,
        "prepare_ref": path.relative_to(root.resolve()).as_posix(),
        "prepare_sha256": digest,
    }


def validate_completed_transaction(
    root: Path,
    transaction_id: str,
    *,
    require_current_targets: bool = True,
) -> dict[str, Any]:
    receipt_path = completion_path(root, transaction_id)
    if not receipt_path.is_file():
        raise SystemExit("Replacement completion receipt is missing.")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Replacement completion receipt is unreadable.") from exc
    if not isinstance(receipt, dict):
        raise SystemExit("Replacement completion receipt must be a JSON object.")
    prepare, prepare_file, prepare_digest = _validated_prepare(root, transaction_id)
    if receipt.get("schema_version") != REPLACEMENT_TRANSACTION_VERSION:
        raise SystemExit("Replacement completion receipt schema version is unsupported.")
    if receipt.get("receipt_kind") != "task_pack_replacement":
        raise SystemExit("Replacement completion receipt kind is invalid.")
    if receipt.get("transaction_id") != transaction_id or receipt.get("status") != "committed":
        raise SystemExit("Replacement completion receipt state is invalid.")
    if receipt.get("prepare_ref") != prepare_file.relative_to(root.resolve()).as_posix():
        raise SystemExit("Replacement completion receipt prepare ref is inconsistent.")
    if receipt.get("prepare_sha256") != prepare_digest:
        raise SystemExit("Replacement completion receipt prepare digest is inconsistent.")
    metadata = prepare.get("metadata") if isinstance(prepare.get("metadata"), dict) else {}
    if receipt.get("plan_fingerprint") != metadata.get("plan_fingerprint"):
        raise SystemExit("Replacement completion receipt plan fingerprint is inconsistent.")
    expected_targets = _target_projection(prepare["targets"])
    if receipt.get("targets") != expected_targets:
        raise SystemExit("Replacement completion receipt target projection is inconsistent.")
    if receipt.get("postcondition") != _historical_postcondition(prepare):
        raise SystemExit("Replacement completion receipt postcondition is inconsistent with prepared after-state.")
    if require_current_targets:
        for target in prepare["targets"]:
            path = _bounded_pack_target(root, str(target["target_ref"]))
            if sha256_file(path) != target["after_sha256"]:
                raise SystemExit("Replacement completion target no longer matches the committed receipt.")
    return {**receipt, "receipt_ref": receipt_path.relative_to(root.resolve()).as_posix(), "receipt_sha256": sha256_file(receipt_path)}


def publish_transaction(
    root: Path,
    transaction_id: str,
    *,
    postcondition: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    receipt_path = completion_path(root, transaction_id)
    if receipt_path.is_file():
        return validate_completed_transaction(root, transaction_id)
    prepare, prepare_file, prepare_digest = _validated_prepare(root, transaction_id)
    for target in prepare["targets"]:
        path = _bounded_pack_target(root, str(target["target_ref"]))
        current = sha256_file(path)
        before = target.get("before_sha256")
        after = str(target["after_sha256"])
        if current == after:
            continue
        if current != before:
            raise SystemExit(
                f"Replacement target drifted outside its exact before/after states: {target['target_ref']}"
            )
        payload = base64.b64decode(str(target["after_payload_b64"]), validate=True)
        atomic_write_bytes(path, payload)
        if sha256_file(path) != after:
            raise SystemExit(f"Replacement target failed post-write verification: {target['target_ref']}")
    postcondition_result = postcondition(prepare) if postcondition is not None else {}
    receipt = {
        "schema_version": REPLACEMENT_TRANSACTION_VERSION,
        "receipt_kind": "task_pack_replacement",
        "transaction_id": transaction_id,
        "status": "committed",
        "prepare_ref": prepare_file.relative_to(root.resolve()).as_posix(),
        "prepare_sha256": prepare_digest,
        "plan_fingerprint": (prepare.get("metadata") or {}).get("plan_fingerprint"),
        "targets": [
            {
                "role": target["role"],
                "target_ref": target["target_ref"],
                "before_sha256": target.get("before_sha256"),
                "after_sha256": target["after_sha256"],
            }
            for target in prepare["targets"]
        ],
        "postcondition": postcondition_result,
    }
    receipt_digest = _write_once(receipt_path, json_bytes(receipt), "Replacement completion receipt")
    return {**receipt, "receipt_ref": receipt_path.relative_to(root.resolve()).as_posix(), "receipt_sha256": receipt_digest}


def recover_pending_transactions(
    root: Path,
    *,
    postcondition: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return [publish_transaction(root, transaction_id, postcondition=postcondition) for transaction_id in pending_transaction_ids(root)]
