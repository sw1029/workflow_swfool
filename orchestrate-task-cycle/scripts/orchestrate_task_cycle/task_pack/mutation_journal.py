"""Durable single-pack mutation prepare/commit/recovery receipts."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from .packet_io import write_bytes_atomic
from .storage import (
    _require_within,
    bounded_workspace_file,
    canonical_pack_sha256,
    json_bytes,
    pack_dir,
    preserve_content_addressed_evidence,
    rel_path,
    sha256_bytes,
    sha256_file,
    sha256_optional_file,
)


MUTATION_TRANSACTION_VERSION = 1
TRANSACTION_ID_PATTERN = re.compile(r"^mutation-([0-9a-f]{64})-([0-9a-f]{64})$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def plan_fingerprint(plan: dict[str, Any]) -> str:
    return sha256_bytes(json_bytes(plan))


def _transaction_root(root: Path) -> Path:
    return pack_dir(root) / "mutation_transactions"


def _receipt_root(root: Path) -> Path:
    return pack_dir(root) / "mutation_receipts"


def prepare_path(root: Path, transaction_id: str) -> Path:
    if not TRANSACTION_ID_PATTERN.fullmatch(transaction_id):
        raise SystemExit("Task-pack mutation transaction id is invalid.")
    return _transaction_root(root) / transaction_id / "prepare.json"


def completion_path(root: Path, transaction_id: str) -> Path:
    if not TRANSACTION_ID_PATTERN.fullmatch(transaction_id):
        raise SystemExit("Task-pack mutation transaction id is invalid.")
    return _receipt_root(root) / f"{transaction_id}.json"


def _write_once(path: Path, payload: bytes, label: str) -> str:
    digest = sha256_bytes(payload)
    if path.exists():
        if not path.is_file() or sha256_file(path) != digest:
            raise SystemExit(f"{label} conflicts with immutable transaction evidence.")
        return digest
    write_bytes_atomic(path, payload)
    if sha256_file(path) != digest:
        raise SystemExit(f"{label} failed post-write verification.")
    return digest


def _bounded_target(root: Path, reference: str) -> Path:
    raw = Path(str(reference or "").strip())
    if not str(reference or "").strip() or raw.is_absolute():
        raise SystemExit("Task-pack mutation target must be workspace-relative.")
    path = _require_within(
        root.resolve() / raw, pack_dir(root), "Task-pack mutation target"
    )
    if path.suffix != ".json":
        raise SystemExit("Task-pack mutation target must be a JSON pack.")
    return path


def _binding(metadata: dict[str, Any]) -> str:
    return sha256_bytes(json_bytes(metadata))


def _verify_bound_file(root: Path, reference: Any, digest: Any, label: str) -> None:
    normalized = str(digest or "").removeprefix("sha256:")
    if not SHA256_PATTERN.fullmatch(normalized):
        raise SystemExit(f"{label} digest is invalid.")
    path = bounded_workspace_file(root, reference, label)
    if sha256_file(path) != normalized:
        raise SystemExit(
            f"{label} is missing or no longer matches its prepared digest."
        )


def _validate_prepared_evidence(root: Path, body: dict[str, Any]) -> None:
    for item in body.get("items", []):
        if not isinstance(item, dict):
            continue
        promotion = item.get("promotion")
        if isinstance(promotion, dict) and promotion.get("task_snapshot_path"):
            _verify_bound_file(
                root,
                promotion.get("task_snapshot_path"),
                promotion.get("task_sha256"),
                "Prepared promotion task snapshot",
            )
            initial = promotion.get("initial_selection_receipt")
            if isinstance(initial, dict):
                for ref_key, sha_key, label in (
                    (
                        "pack_creation_snapshot_ref",
                        "pack_creation_snapshot_sha256",
                        "Prepared creation snapshot",
                    ),
                    (
                        "authority_receipt_ref",
                        "authority_receipt_sha256",
                        "Prepared authority receipt",
                    ),
                ):
                    if initial.get(ref_key):
                        _verify_bound_file(
                            root, initial.get(ref_key), initial.get(sha_key), label
                        )
        completion = item.get("completion")
        if isinstance(completion, dict):
            for ref_key, sha_key, label in (
                ("run_report_path", "run_report_sha256", "Prepared run report"),
                (
                    "validation_report_path",
                    "validation_report_sha256",
                    "Prepared validation report",
                ),
                ("issue_packet_path", "issue_packet_sha256", "Prepared issue packet"),
            ):
                if completion.get(ref_key):
                    _verify_bound_file(
                        root, completion.get(ref_key), completion.get(sha_key), label
                    )


def _load_prepare(root: Path, transaction_id: str) -> tuple[dict[str, Any], Path, str]:
    path = prepare_path(root, transaction_id)
    if not path.is_file():
        raise SystemExit("Task-pack mutation prepare journal is missing.")
    try:
        prepare = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Task-pack mutation prepare journal is unreadable.") from exc
    if not isinstance(prepare, dict):
        raise SystemExit("Task-pack mutation prepare journal must be an object.")
    metadata = prepare.get("metadata")
    if (
        prepare.get("schema_version") != MUTATION_TRANSACTION_VERSION
        or prepare.get("receipt_kind") != "task_pack_mutation_prepare"
        or prepare.get("transaction_id") != transaction_id
        or not isinstance(metadata, dict)
    ):
        raise SystemExit("Task-pack mutation prepare journal contract is invalid.")
    match = TRANSACTION_ID_PATTERN.fullmatch(transaction_id)
    if (
        match is None
        or match.group(1) != metadata.get("plan_fingerprint")
        or match.group(2) != _binding(metadata)
    ):
        raise SystemExit("Task-pack mutation prepare journal binding is invalid.")
    for field in (
        "plan_fingerprint",
        "target_ref",
        "after_file_sha256",
        "after_pack_sha256",
    ):
        if not metadata.get(field):
            raise SystemExit(f"Task-pack mutation prepare metadata is missing {field}.")
    _bounded_target(root, str(metadata["target_ref"]))
    try:
        payload = base64.b64decode(
            str(prepare.get("after_payload_b64") or ""), validate=True
        )
    except ValueError as exc:
        raise SystemExit(
            "Task-pack mutation prepared payload is invalid base64."
        ) from exc
    if sha256_bytes(payload) != metadata.get("after_file_sha256"):
        raise SystemExit("Task-pack mutation prepared payload digest is invalid.")
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "Task-pack mutation prepared payload is not valid JSON."
        ) from exc
    if not isinstance(body, dict) or canonical_pack_sha256(body) != metadata.get(
        "after_pack_sha256"
    ):
        raise SystemExit("Task-pack mutation prepared canonical digest is invalid.")
    _validate_prepared_evidence(root, body)
    return prepare, path, sha256_file(path)


def prepare_mutation(
    root: Path,
    *,
    action: str,
    plan: dict[str, Any],
    target_path: Path,
    after_data: dict[str, Any],
    before_pack_sha256: str | None,
    coherence_receipt: dict[str, Any],
) -> dict[str, Any]:
    target_ref = rel_path(root, target_path)
    _bounded_target(root, target_ref)
    payload = json_bytes(after_data)
    fingerprint = plan_fingerprint(plan)
    metadata = {
        "action": action,
        "plan_fingerprint": fingerprint,
        "target_ref": target_ref,
        "before_file_sha256": sha256_optional_file(target_path),
        "before_pack_sha256": before_pack_sha256,
        "after_file_sha256": sha256_bytes(payload),
        "after_pack_sha256": canonical_pack_sha256(after_data),
        "coherence_receipt": coherence_receipt,
    }
    transaction_id = f"mutation-{fingerprint}-{_binding(metadata)}"
    prepare = {
        "schema_version": MUTATION_TRANSACTION_VERSION,
        "receipt_kind": "task_pack_mutation_prepare",
        "transaction_id": transaction_id,
        "metadata": metadata,
        "after_payload_b64": base64.b64encode(payload).decode("ascii"),
    }
    path = prepare_path(root, transaction_id)
    digest = _write_once(
        path, json_bytes(prepare), "Task-pack mutation prepare journal"
    )
    _load_prepare(root, transaction_id)
    preserve_content_addressed_evidence()
    return {
        "transaction_id": transaction_id,
        "prepare_ref": rel_path(root, path),
        "prepare_sha256": digest,
    }


def validate_completed_transaction(
    root: Path,
    transaction_id: str,
    *,
    require_current_target: bool = True,
) -> dict[str, Any]:
    receipt_path = completion_path(root, transaction_id)
    if not receipt_path.is_file():
        raise SystemExit("Task-pack mutation completion receipt is missing.")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "Task-pack mutation completion receipt is unreadable."
        ) from exc
    prepare, prepare_file, prepare_digest = _load_prepare(root, transaction_id)
    metadata = prepare["metadata"]
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema_version") != MUTATION_TRANSACTION_VERSION
        or receipt.get("receipt_kind") != "task_pack_mutation"
        or receipt.get("transaction_id") != transaction_id
        or receipt.get("status") != "committed"
        or receipt.get("prepare_ref") != rel_path(root, prepare_file)
        or receipt.get("prepare_sha256") != prepare_digest
        or receipt.get("plan_fingerprint") != metadata.get("plan_fingerprint")
        or receipt.get("target_ref") != metadata.get("target_ref")
        or receipt.get("after_file_sha256") != metadata.get("after_file_sha256")
        or receipt.get("after_pack_sha256") != metadata.get("after_pack_sha256")
        or receipt.get("coherence_receipt") != metadata.get("coherence_receipt")
    ):
        raise SystemExit("Task-pack mutation completion receipt contract is invalid.")
    if require_current_target:
        target = _bounded_target(root, str(metadata["target_ref"]))
        if sha256_optional_file(target) != metadata["after_file_sha256"]:
            raise SystemExit(
                "Task-pack mutation target no longer matches its completion receipt."
            )
    return {
        **receipt,
        "receipt_ref": rel_path(root, receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
    }


def publish_transaction(root: Path, transaction_id: str) -> dict[str, Any]:
    receipt_path = completion_path(root, transaction_id)
    if receipt_path.is_file():
        return validate_completed_transaction(root, transaction_id)
    prepare, prepare_file, prepare_digest = _load_prepare(root, transaction_id)
    metadata = prepare["metadata"]
    target = _bounded_target(root, str(metadata["target_ref"]))
    current = sha256_optional_file(target)
    if current != metadata.get("after_file_sha256"):
        if current != metadata.get("before_file_sha256"):
            raise SystemExit(
                "Task-pack mutation target drifted outside its prepared before/after states."
            )
        payload = base64.b64decode(str(prepare["after_payload_b64"]), validate=True)
        write_bytes_atomic(target, payload)
    if sha256_file(target) != metadata["after_file_sha256"]:
        raise SystemExit("Task-pack mutation target failed post-write verification.")
    receipt = {
        "schema_version": MUTATION_TRANSACTION_VERSION,
        "receipt_kind": "task_pack_mutation",
        "transaction_id": transaction_id,
        "status": "committed",
        "prepare_ref": rel_path(root, prepare_file),
        "prepare_sha256": prepare_digest,
        "action": metadata.get("action"),
        "plan_fingerprint": metadata.get("plan_fingerprint"),
        "target_ref": metadata.get("target_ref"),
        "before_file_sha256": metadata.get("before_file_sha256"),
        "before_pack_sha256": metadata.get("before_pack_sha256"),
        "after_file_sha256": metadata.get("after_file_sha256"),
        "after_pack_sha256": metadata.get("after_pack_sha256"),
        "coherence_receipt": metadata.get("coherence_receipt"),
    }
    digest = _write_once(
        receipt_path, json_bytes(receipt), "Task-pack mutation completion receipt"
    )
    return {
        **receipt,
        "receipt_ref": rel_path(root, receipt_path),
        "receipt_sha256": digest,
    }


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
        if not completion_path(root, child.name).is_file():
            pending.append(child.name)
            continue
        try:
            validate_completed_transaction(
                root, child.name, require_current_target=False
            )
        except SystemExit:
            pending.append(child.name)
    return pending


def recover_pending_transactions(root: Path) -> list[dict[str, Any]]:
    return [
        publish_transaction(root, transaction_id)
        for transaction_id in pending_transaction_ids(root)
    ]


def completed_for_plan(root: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    fingerprint = plan_fingerprint(plan)
    directory = _receipt_root(root)
    if not directory.is_dir():
        return []
    receipts: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"mutation-{fingerprint}-*.json")):
        if path.is_file():
            receipts.append(validate_completed_transaction(root, path.stem))
    return receipts


def validate_receipt_binding(
    root: Path,
    plan: dict[str, Any],
    coherence_receipt: dict[str, Any],
) -> dict[str, Any]:
    durable_ref = str(coherence_receipt.get("durable_receipt_ref") or "")
    durable_sha = str(coherence_receipt.get("durable_receipt_sha256") or "")
    if not durable_ref or not SHA256_PATTERN.fullmatch(durable_sha):
        raise SystemExit(
            "Current task-pack mutation receipt requires durable receipt ref and SHA-256."
        )
    if Path(durable_ref).is_absolute():
        raise SystemExit(
            "Durable task-pack mutation receipt ref must be workspace-relative."
        )
    durable_path = _require_within(
        root.resolve() / durable_ref, _receipt_root(root), "Durable mutation receipt"
    )
    if not durable_path.is_file() or sha256_file(durable_path) != durable_sha:
        raise SystemExit(
            "Durable task-pack mutation receipt is missing or has a stale digest."
        )
    durable = validate_completed_transaction(root, durable_path.stem)
    if durable.get("plan_fingerprint") != plan_fingerprint(plan):
        raise SystemExit(
            "Durable task-pack mutation receipt is bound to a different plan."
        )
    expected_coherence = {
        key: value
        for key, value in coherence_receipt.items()
        if key not in {"durable_receipt_ref", "durable_receipt_sha256"}
    }
    if durable.get("coherence_receipt") != expected_coherence:
        raise SystemExit(
            "Durable task-pack mutation receipt is bound to a different coherence receipt."
        )
    return durable


def commit_pack_mutation(
    root: Path,
    *,
    action: str,
    plan: dict[str, Any],
    target_path: Path,
    after_data: dict[str, Any],
    before_pack_sha256: str | None,
    coherence_receipt: dict[str, Any],
) -> dict[str, Any]:
    prepared = prepare_mutation(
        root,
        action=action,
        plan=plan,
        target_path=target_path,
        after_data=after_data,
        before_pack_sha256=before_pack_sha256,
        coherence_receipt=coherence_receipt,
    )
    return publish_transaction(root, str(prepared["transaction_id"]))
