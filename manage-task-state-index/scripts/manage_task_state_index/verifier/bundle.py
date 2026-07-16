"""Load and bind a published migration bundle to caller-owned evidence."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .core import (
    VerificationError,
    _canonical_json,
    _hashed_transaction_ref,
    _is_int,
    _is_sha256,
    _load_json,
    _regular_file,
    _require,
    _root,
    _sha256_path,
    _transaction_ref,
    _workspace_ref,
)
from .graph_contracts import RECEIPT_KEYS
from .mapping_evidence import _validate_mapping

def _canonical_document(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    document, payload = _load_json(path, label)
    _require(payload == _canonical_json(document), f"{label} is not canonical JSON")
    return document, payload

def _load_bundle(root_raw: str | Path, receipt_raw: str | Path) -> dict[str, Any]:
    root = _root(root_raw)
    receipt_path = Path(receipt_raw)
    if not receipt_path.is_absolute():
        receipt_relative = receipt_path.as_posix()
    else:
        try:
            receipt_relative = receipt_path.absolute().relative_to(root).as_posix()
        except ValueError as exc:
            raise VerificationError("receipt must be workspace-local") from exc
    receipt_path = _workspace_ref(root, receipt_relative, "receipt")
    receipt, receipt_payload = _canonical_document(receipt_path, "receipt")
    _require(set(receipt) == RECEIPT_KEYS, "receipt has unknown or missing fields")
    transaction_id = receipt.get("transaction_id")
    _require(
        isinstance(transaction_id, str) and re.fullmatch(r"tsm-[0-9a-f]{24}", transaction_id) is not None,
        "receipt transaction identity is invalid",
    )
    _require(
        _transaction_ref(root, receipt_relative, transaction_id, "receipt") == receipt_path,
        "receipt is outside its transaction",
    )
    _require(
        _is_int(receipt.get("schema_version")) and receipt["schema_version"] == 2
        and receipt.get("kind") == "task_state_index_migration"
        and receipt.get("status") == "committed",
        "receipt is not the exact committed schema-v2 contract",
    )
    for field in (
        "source_prefix_byte_length", "source_raw_row_count", "accepted_current_count",
        "normalized_legacy_count", "mapped_legacy_count", "quarantined_historical_count",
        "blocked_count", "correction_suffix_byte_length", "correction_suffix_count",
        "correction_suffix_offset", "seal_offset", "seal_byte_length", "commit_boundary_length",
        "active_task_count", "active_pack_count", "duplicate_active_alias_count",
        "current_broken_link_count", "before_active_task_count", "before_active_pack_count",
        "before_duplicate_active_alias_count", "before_current_broken_link_count",
        "current_surface_blocker_count",
    ):
        _require(_is_int(receipt.get(field)) and receipt[field] >= 0, f"receipt {field} type is invalid")
    for field in (
        "source_prefix_sha256", "mapping_manifest_sha256", "resolution_manifest_sha256",
        "plan_sha256", "plan_contract_sha256", "correction_suffix_sha256", "seal_sha256",
        "commit_boundary_sha256", "superseded_task_id_digest", "superseded_pack_id_digest",
        "retracted_link_pair_digest", "rendered_index_sha256", "prepare_journal_sha256",
        "journal_sha256", "completion_marker_sha256",
    ):
        _require(_is_sha256(receipt.get(field)), f"receipt {field} hash is invalid")
    _require(
        receipt.get("prefix_preserved") is True
        and receipt.get("current_active_pack_indexed") is True,
        "receipt boolean contract is invalid",
    )
    refs: dict[str, tuple[Path, bytes]] = {}
    for label, ref_field, sha_field in (
        ("source_prefix", "source_prefix_ref", "source_prefix_sha256"),
        ("mapping_manifest", "mapping_manifest_ref", "mapping_manifest_sha256"),
        ("correction_suffix", "correction_suffix_ref", "correction_suffix_sha256"),
        ("rendered_index", "rendered_index_ref", "rendered_index_sha256"),
        ("prepare_journal", "prepare_journal_ref", "prepare_journal_sha256"),
        ("journal", "journal_ref", "journal_sha256"),
        ("completion_marker", "completion_marker_ref", "completion_marker_sha256"),
    ):
        refs[label] = _hashed_transaction_ref(
            root, receipt, ref_field, sha_field, transaction_id, label
        )
    resolution_path = _transaction_ref(
        root, receipt["resolution_manifest_ref"], transaction_id,
        "resolution_manifest",
    )
    _require(
        _sha256_path(resolution_path) == receipt["resolution_manifest_sha256"],
        "resolution_manifest hash mismatch",
    )
    refs["resolution_manifest"] = (resolution_path, b"")
    plan_path = _transaction_ref(root, receipt["plan_ref"], transaction_id, "plan")
    _require(_sha256_path(plan_path) == receipt["plan_sha256"], "plan hash mismatch")
    try:
        with plan_path.open("r", encoding="utf-8") as handle:
            plan_document = json.load(handle)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"plan is not valid UTF-8 JSON: {exc}") from exc
    _require(isinstance(plan_document, dict), "plan must be an object")
    refs["plan"] = (plan_path, b"")
    documents = {
        "mapping_manifest": _load_json(refs["mapping_manifest"][0], "mapping_manifest")[0],
        **{
            label: _canonical_document(refs[label][0], label)[0]
            for label in ("prepare_journal", "journal", "completion_marker")
        },
        "plan": plan_document,
    }
    return {
        "root": root,
        "receipt": receipt,
        "receipt_path": receipt_path,
        "receipt_relative": receipt_relative,
        "receipt_payload": receipt_payload,
        "plan_sha256": receipt["plan_sha256"],
        "transaction_id": transaction_id,
        "refs": refs,
        **documents,
    }

def _external_mapping(
    bundle: dict[str, Any], expected_mapping_raw: str | Path
) -> tuple[dict[str, Any], bytes, Path]:
    root = bundle["root"]
    _require(
        isinstance(expected_mapping_raw, (str, Path)),
        "caller-owned mapping manifest is required",
    )
    raw_path = Path(expected_mapping_raw).expanduser()
    if not raw_path.is_absolute():
        raw_path = root / raw_path
    lexical = raw_path.absolute()
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        _require(not current.is_symlink(), "caller-owned mapping manifest contains a symlink")
    expected_path = _regular_file(raw_path.resolve(strict=True), "caller-owned mapping manifest")
    parts = expected_path.parts
    _require(
        not any(parts[index:index + 2] == (".task", "migrations") for index in range(len(parts) - 1)),
        "caller-owned mapping must remain outside every task-state transaction tree",
    )
    snapshot_path, snapshot_payload = bundle["refs"]["mapping_manifest"]
    _require(not expected_path.samefile(snapshot_path), "caller-owned mapping aliases the published snapshot")
    _require(
        expected_path.stat().st_nlink == 1 and snapshot_path.stat().st_nlink == 1,
        "mapping trust anchors must not be hard-linked",
    )
    expected_document, expected_payload = _load_json(expected_path, "caller-owned mapping manifest")
    _validate_mapping(expected_document)
    _require(expected_payload == snapshot_payload, "published mapping differs from the caller-owned exact mapping")
    return expected_document, expected_payload, expected_path
