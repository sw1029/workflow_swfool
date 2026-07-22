"""Forward-recoverable publication of one canonical task selection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .selection_publication_prepare import (
    committed_replay,
    pending_replay,
    validate_publish_predecessor,
)
from .selection_publication_plan import (
    MAX_TARGET_BYTES as MAX_TARGET_BYTES,
    MAX_TOTAL_BYTES as MAX_TOTAL_BYTES,
    OPAQUE_ID as OPAQUE_ID,
    OWNER_COMMITTED_PROJECTION_ROLES as OWNER_COMMITTED_PROJECTION_ROLES,
    ROLE_PRIORITY as ROLE_PRIORITY,
    SHA256 as SHA256,
    _decode_payload,
    _normalize_plan,
    _role_path_allowed as _role_path_allowed,
    _target_path,
)
from .selection_publication_intent_index import (
    load_intent_index,
    write_commit_index,
)
from .selection_publication_receipt import (
    receipt_for_prepare,
    validate_receipt as _validate_receipt_contract,
)
from .selection_publication_state import (
    STORAGE_SCHEMA_VERSION,
    head_receipts,
    load_state,
    record_committed,
    write_empty_state,
    write_state,
)
from .selection_publication_store import (
    TRANSACTION_ID,
    _atomic_write,
    _canonical_json,
    _display_json,
    _lock,
    _prepare_path,
    _receipts_root,
    _receipt_path,
    _sha256_bytes,
    _sha256_file,
    _transactions_root,
    _write_once,
)
from .selection_publication_v2 import (
    normalize_prepare as normalize_v2_prepare,
    payload_for_target,
    validate_external_pending_assertion,
    validate_owner_assertion,
)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _load_prepare(root: Path, transaction_id: str) -> tuple[dict[str, Any], Path, str]:
    path = _prepare_path(root, transaction_id)
    prepare = _load_json(path, "selection-publication prepare journal")
    if prepare.get("transaction_id") != transaction_id:
        raise ValueError("selection-publication prepare transaction id is inconsistent")
    if prepare.get("schema_version") in {2, 3}:
        normalized = normalize_v2_prepare(root, prepare)
    else:
        plan_material = {
            key: value
            for key, value in prepare.items()
            if key not in {"transaction_id", "predecessor_transaction_id"}
        }
        plan_material["kind"] = "selection_publication_plan"
        normalized = _normalize_plan(
            root,
            plan_material,
            require_current_owner_projections=False,
        )
    if "predecessor_transaction_id" in prepare:
        predecessor = prepare.get("predecessor_transaction_id")
        if predecessor is not None and not TRANSACTION_ID.fullmatch(str(predecessor)):
            raise ValueError("selection-publication predecessor transaction is invalid")
        if predecessor == transaction_id:
            raise ValueError("selection-publication transaction cannot precede itself")
        normalized["predecessor_transaction_id"] = predecessor
    normalized["transaction_id"] = transaction_id
    if prepare != normalized:
        raise ValueError("selection-publication prepare journal is non-canonical")
    transaction_material = {
        key: value for key, value in normalized.items() if key != "transaction_id"
    }
    expected_id = "selection-" + _sha256_bytes(_canonical_json(transaction_material))
    if expected_id != transaction_id:
        raise ValueError("selection-publication prepare journal binding is invalid")
    digest = _sha256_file(path)
    assert digest is not None
    return prepare, path, digest


def prepare_publication(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """Replay legacy v1 evidence, but never create a new v1 transaction.

    Inline/Base64 plans are retained solely as a recovery reader. New selected
    successors must enter through ``prepare_publication_intent``.
    """

    root = root.expanduser().resolve(strict=True)
    normalized = _normalize_plan(root, plan)
    with _lock(root):
        state = _load_or_initialize_state(root)
        replay = pending_replay(
            root,
            normalized,
            _state_pending_ids(state),
            load_prepare=_load_prepare,
        )
        if replay is not None:
            return {**replay, "storage_schema_version": STORAGE_SCHEMA_VERSION}
        receipts = head_receipts(state)
        replay = committed_replay(
            root, normalized, receipts, load_prepare=_load_prepare
        )
        if replay is not None:
            return {**replay, "storage_schema_version": STORAGE_SCHEMA_VERSION}
        raise ValueError(
            "legacy selection-publication v1 new write is forbidden; use a body-free selection publication intent"
        )


def prepare_publication_intent(
    root: Path, intent: dict[str, Any]
) -> dict[str, Any]:
    from .selection_publication_intent_service import prepare_publication_intent as run

    return run(root, intent)


def prepare_drift_reconciliation(
    root: Path, plan: dict[str, Any]
) -> dict[str, Any]:
    """Journal the exact current task bytes as a successor to one drifted head."""

    root = root.expanduser().resolve(strict=True)
    normalized = _normalize_plan(root, plan)
    if len(normalized["targets"]) != 1 or normalized["targets"][0]["role"] != "task_alias":
        raise ValueError(
            "selection-publication drift reconciliation accepts only task_alias"
        )
    return prepare_publication(root, plan)


def validate_receipt(
    root: Path, transaction_id: str, *, require_current_targets: bool = False
) -> dict[str, Any]:
    return _validate_receipt_contract(
        root,
        transaction_id,
        require_current_targets=require_current_targets,
        load_prepare=_load_prepare,
    )


def _historical_receipt_response(root: Path, transaction_id: str) -> dict[str, Any]:
    verified = validate_receipt(root, transaction_id, require_current_targets=False)
    return {
        **verified,
        "mutation_performed": False,
        "authoritative_selection_published": False,
        "current_selection_authority_claimed": False,
        "publication_authority_status": "historical_receipt_only",
        "recovery_required": False,
    }


def _repair_existing_receipt(
    root: Path,
    state: dict[str, Any],
    transaction_id: str,
    receipt_path: Path,
) -> dict[str, Any]:
    response = _historical_receipt_response(root, transaction_id)
    prepare, prepare_path, prepare_sha = _load_prepare(root, transaction_id)
    receipt_sha = _sha256_file(receipt_path)
    assert receipt_sha is not None
    repaired_state = False
    repaired_commit_index = False
    active = state.get("active_transaction")
    if isinstance(active, dict) and active.get("transaction_id") == transaction_id:
        record_committed(root, state, prepare, prepare_sha, receipt_sha)
        repaired_state = True
    head = state.get("head")
    head_matches = (
        repaired_state
        or isinstance(head, dict)
        and head.get("transaction_id") == transaction_id
        and head.get("receipt")
        == {
            "ref": receipt_path.relative_to(root).as_posix(),
            "sha256": receipt_sha,
        }
    )
    intent_sha256 = prepare.get("intent_sha256")
    if (
        head_matches
        and isinstance(intent_sha256, str)
        and load_intent_index(root, intent_sha256, committed=True) is None
    ):
        write_commit_index(
            root,
            intent_sha256,
            transaction_id,
            prepare_path,
            prepare_sha,
            receipt_path,
            receipt_sha,
        )
        repaired_commit_index = True
    if repaired_state or repaired_commit_index:
        response = {
            **response,
            "mutation_performed": True,
            "compact_state_repaired": repaired_state,
            "commit_index_repaired": repaired_commit_index,
        }
    return {**response, "storage_schema_version": STORAGE_SCHEMA_VERSION}


def publish_prepared(
    root: Path,
    transaction_id: str,
    *,
    _selected_successor_execution_token: object | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    with _lock(root):
        try:
            state = load_state(root)
        except ValueError as exc:
            if "migration required" not in str(exc):
                raise
            state = None
        if state is None:
            # An explicit transaction ID is a recovery instruction. It may
            # perform the one permitted deep scan needed to bind legacy history.
            if not _prepare_path(root, transaction_id).is_file():
                raise ValueError("selection-publication prepare journal is missing")
            receipts = _committed_receipts(root)
            pending = _deep_pending_transaction_ids(root)
            state = write_state(root, receipts, pending, load_prepare=_load_prepare)
        prepare, prepare_path, prepare_sha = _load_prepare(root, transaction_id)
        if prepare.get("schema_version") == 3:
            from manage_task_state_index.state.selected_successor_guard import (
                require_selected_successor_execution,
            )

            require_selected_successor_execution(
                _selected_successor_execution_token
            )
        receipt_path = _receipt_path(root, transaction_id)
        if receipt_path.is_file():
            return _repair_existing_receipt(
                root, state, transaction_id, receipt_path
            )
        _reject_competing_pending(state, transaction_id)
        validate_publish_predecessor(
            prepare,
            head_receipts(state),
            _sha256_file(root / "task.md"),
        )
        targets = list(prepare["targets"])
        pending_binding: dict[str, str] | None = None
        if prepare.get("schema_version") == 2:
            for assertion in prepare["owner_assertions"]:
                validate_owner_assertion(root, assertion)
        elif prepare.get("schema_version") == 3:
            pending_binding = validate_external_pending_assertion(
                root,
                prepare,
                {
                    "ref": prepare_path.relative_to(root).as_posix(),
                    "sha256": prepare_sha,
                },
            )
        for target in targets:
            current = _sha256_file(
                _target_path(root, target["role"], target["target_ref"])
            )
            if current not in {target.get("before_sha256"), target["after_sha256"]}:
                raise ValueError(
                    f"selection-publication target drifted outside prepared states: {target['target_ref']}"
                )
        for target in targets:  # canonical pointer is sorted last by ROLE_PRIORITY.
            path = _target_path(root, target["role"], target["target_ref"])
            if _sha256_file(path) == target["after_sha256"]:
                continue
            payload = (
                payload_for_target(root, target)
                if prepare.get("schema_version") in {2, 3}
                else _decode_payload(target)
            )
            _atomic_write(path, payload)
            if _sha256_file(path) != target["after_sha256"]:
                raise ValueError(
                    "selection-publication target failed post-write verification"
                )
        receipt = receipt_for_prepare(
            root,
            prepare,
            prepare_path,
            prepare_sha,
            pending_binding=pending_binding,
        )
        receipt_sha = _write_once(
            receipt_path, _display_json(receipt), "selection-publication receipt"
        )
        verified = validate_receipt(root, transaction_id, require_current_targets=True)
        record_committed(root, state, prepare, prepare_sha, receipt_sha)
        intent_sha256 = prepare.get("intent_sha256")
        if isinstance(intent_sha256, str):
            write_commit_index(
                root,
                intent_sha256,
                transaction_id,
                prepare_path,
                prepare_sha,
                receipt_path,
                receipt_sha,
            )
        result = {
            **verified,
            "receipt_sha256": receipt_sha,
            "storage_schema_version": STORAGE_SCHEMA_VERSION,
            "mutation_performed": True,
            "authoritative_selection_published": True,
            "current_selection_authority_claimed": True,
            "publication_authority_status": "published_current",
            "recovery_required": False,
        }
        if prepare.get("schema_version") == 3:
            result.update(
                {
                    "activation_status": "pending_external_settlement",
                    "selection_consumption_allowed": False,
                    "recovery_required": True,
                    "next_action": "settle_task_state_external",
                }
            )
        return result


def pending_transaction_ids(root: Path) -> list[str]:
    root = root.expanduser().resolve(strict=True)
    state = load_state(root)
    if state is not None:
        return _state_pending_ids(state)
    store = root / ".task/selection_publication"
    if store.exists() or store.is_symlink():
        raise ValueError(
            "selection publication state migration required before bounded status or recovery"
        )
    return []


def _deep_pending_transaction_ids(root: Path) -> list[str]:
    """Enumerate history only for explicit deep audit/migration."""

    root = root.expanduser().resolve(strict=True)
    directory = _transactions_root(root)
    if not directory.is_dir():
        return []
    pending: list[str] = []
    for child in sorted(directory.iterdir()):
        if not child.is_dir() or not TRANSACTION_ID.fullmatch(child.name):
            continue
        if not (child / "prepare.json").is_file():
            continue
        try:
            validate_receipt(root, child.name)
        except (OSError, ValueError):
            pending.append(child.name)
    return pending


def _state_pending_ids(state: dict[str, Any]) -> list[str]:
    active = state.get("active_transaction")
    return [str(active["transaction_id"])] if isinstance(active, dict) else []


def _reject_competing_pending(state: dict[str, Any], transaction_id: str) -> None:
    competing = [
        item for item in _state_pending_ids(state) if item != transaction_id
    ]
    if competing:
        raise ValueError(
            "selection-publication has a different pending transaction; "
            "recover it before preparing or publishing new selection work"
        )


def _committed_receipts(root: Path) -> list[dict[str, Any]]:
    directory = _receipts_root(root)
    if not directory.is_dir():
        return []
    receipts: list[dict[str, Any]] = []
    for path in sorted(directory.glob("selection-*.json")):
        transaction_id = path.stem
        if TRANSACTION_ID.fullmatch(transaction_id):
            receipts.append(validate_receipt(root, transaction_id))
    return receipts


def _load_or_initialize_state(root: Path) -> dict[str, Any]:
    state = load_state(root)
    if state is not None:
        return state
    # The lock creates only the store root. Any journal category proves this is
    # pre-v4 history and must be migrated explicitly rather than silently scanned.
    store = root / ".task/selection_publication"
    if any((store / name).exists() for name in ("transactions", "receipts", "intents")):
        raise ValueError(
            "selection publication state migration required; run migrate-state explicitly"
        )
    return write_empty_state(root)


def migrate_publication_state(root: Path) -> dict[str, Any]:
    from .selection_publication_migration import migrate_publication_state as migrate

    return migrate(
        root,
        committed_receipts=_committed_receipts,
        deep_pending_ids=_deep_pending_transaction_ids,
        load_prepare=_load_prepare,
    )


def recover_publications(
    root: Path, transaction_id: str | None = None
) -> dict[str, Any]:
    from .selection_publication_runtime import recover_publications as recover

    return recover(root, transaction_id)


def publication_status(root: Path, *, deep: bool = False) -> dict[str, Any]:
    from .selection_publication_runtime import publication_status as status

    return status(root, deep=deep)
