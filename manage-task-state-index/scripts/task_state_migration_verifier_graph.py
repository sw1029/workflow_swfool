"""Independent graph, publication, identity, and recovery-boundary checks."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re
from typing import Any

from task_state_migration_verifier_core import (
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    MIGRATION_EVENT_FIELD,
    SEAL_KIND,
    SHA256_LENGTH,
    TOOL_VERSIONS,
    VerificationError,
    _canonical_json,
    _event_bytes,
    _hashed_transaction_ref,
    _is_int,
    _is_sha256,
    _load_json,
    _merge_event_into_state,
    _merge_state,
    _opaque_identity_token,
    _physical_lines,
    _regular_file,
    _require,
    _root,
    _sha256,
    _sha256_path,
    _transaction_ref,
    _validate_suffix_event,
    _workspace_ref,
    _versioned,
)
from task_state_migration_verifier_evidence import (
    _anchor_event,
    _bind_quarantine_corrections,
    _classify_prefix,
    _current_projection,
    _make_corrections,
    _manifest,
    _render_markdown,
    _validate_mapping,
    _validate_quarantine_bindings,
)
from task_state_migration_verifier_recovery import (
    _boundary_observation_sha256,
    _owned_write_set_sha,
    inspect_transaction_boundary,
    verify_recovery_observation,
)


PLAN_KEYS = {
    "schema_version", "kind", "tool_version", "migration_id", "root_identity",
    "source_prefix", "mapping_manifest", "resolution_manifest", "source_snapshot_ref",
    "plan_snapshot_ref", "classification_counts", "unclassified_count", "rows",
    "correction_events", "projection", "anchors", "effective_at",
    "transaction_directory_ref", "historical_rows_removed", "historical_rows_reordered",
    "original_row_bytes_modified", "prefix_preserved", "plan_contract_sha256",
    "correction_suffix", "seal", "expected_after_index_sha256",
    "expected_commit_boundary_byte_length", "receipt_ref", "receipt_anchor_id",
    "journal_ref", "prepare_journal_ref", "completion_marker_ref", "render_snapshot_ref",
}
PLAN_CORE_KEYS = {
    "schema_version", "kind", "tool_version", "migration_id", "root_identity",
    "source_prefix", "mapping_manifest", "resolution_manifest", "source_snapshot_ref",
    "plan_snapshot_ref", "classification_counts", "unclassified_count", "rows",
    "correction_events", "projection", "anchors", "effective_at",
    "transaction_directory_ref", "historical_rows_removed", "historical_rows_reordered",
    "original_row_bytes_modified", "prefix_preserved",
}
RECEIPT_KEYS = {
    "schema_version", "kind", "transaction_id", "tool_version", "transaction_started_at",
    "transaction_committed_at", "status", "source_prefix_ref", "source_prefix_sha256",
    "source_prefix_byte_length", "source_raw_row_count", "accepted_current_count",
    "normalized_legacy_count", "mapped_legacy_count", "quarantined_historical_count",
    "blocked_count", "mapping_manifest_ref", "mapping_manifest_sha256",
    "resolution_manifest_ref", "resolution_manifest_sha256", "plan_ref", "plan_sha256",
    "plan_contract_sha256", "correction_suffix_ref", "correction_suffix_sha256",
    "correction_suffix_byte_length", "correction_suffix_count", "correction_suffix_offset",
    "seal_id", "seal_sha256", "seal_offset", "seal_byte_length", "commit_boundary_length",
    "commit_boundary_sha256", "prefix_preserved", "historical_rows_removed",
    "historical_rows_reordered", "original_row_bytes_modified", "canonical_task",
    "canonical_pack", "superseded_task_id_digest", "superseded_pack_id_digest",
    "retracted_link_pair_digest", "active_task_count", "active_pack_count",
    "duplicate_active_alias_count", "current_broken_link_count", "before_active_task_count",
    "before_active_pack_count", "before_duplicate_active_alias_count",
    "before_current_broken_link_count", "current_active_pack_indexed",
    "current_projection_status", "projection_completeness", "current_surface_blocker_count",
    "strict_reader_status", "append_simulation_status", "audit_status", "rendered_index_ref",
    "rendered_index_sha256", "prepare_journal_ref", "prepare_journal_sha256", "journal_ref",
    "journal_sha256", "completion_marker_ref", "completion_marker_sha256", "recovery_status",
}
MANIFEST_KEYS = {
    "schema_version", "kind", "migration_id", "source_prefix_sha256",
    "source_prefix_byte_length", "source_raw_row_count", "classification_counts",
    "rows", "raw_row_bodies_included",
}
PREPARE_KEYS = {
    "schema_version", "kind", "transaction_id", "state", "prefix_sha256",
    "prefix_byte_length", "expected_boundary_sha256", "expected_boundary_byte_length",
    "plan_ref", "plan_sha256",
}
JOURNAL_KEYS = PREPARE_KEYS | {
    "journal_updated_at", "receipt_ref", "seal_sha256", "commit_boundary_sha256",
    "rendered_index_ref", "rendered_index_sha256", "recovery_status",
}
MARKER_KEYS = {
    "schema_version", "kind", "transaction_id", "state", "committed_at",
    "prepare_journal_ref", "prepare_journal_sha256", "journal_ref", "journal_sha256",
    "receipt_ref", "plan_ref", "plan_sha256", "seal_sha256", "commit_boundary_length",
    "commit_boundary_sha256", "rendered_index_ref", "rendered_index_sha256", "recovery_status",
}
SOURCE_PREFIX_KEYS = {"ref", "sha256", "byte_length", "raw_row_count"}
MAPPING_BINDING_KEYS = {"source_ref", "sha256", "schema_version", "mapping_policy_id", "snapshot_ref"}
REF_SHA_KEYS = {"ref", "sha256"}
CORRECTION_KEYS = {"ref", "sha256", "byte_length", "event_count", "offset"}
SEAL_KEYS = {"id", "event", "line_sha256", "offset", "byte_length"}
ANCHOR_KEYS = {"id", "path", "sha256"}
ROOT_IDENTITY_KEYS = {"resolved_path", "device", "inode"}

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


def _validate_plan_shapes(plan: dict[str, Any]) -> None:
    _require(set(plan) == PLAN_KEYS, "plan has unknown or missing fields")
    _require(
        _is_int(plan.get("schema_version")) and plan["schema_version"] == 2
        and plan.get("kind") == "task_state_index_migration_plan"
        and plan.get("tool_version") in TOOL_VERSIONS,
        "plan header is unsupported",
    )
    nested = (
        (plan.get("source_prefix"), SOURCE_PREFIX_KEYS, "source prefix"),
        (plan.get("mapping_manifest"), MAPPING_BINDING_KEYS, "mapping binding"),
        (plan.get("resolution_manifest"), REF_SHA_KEYS, "resolution binding"),
        (plan.get("correction_suffix"), CORRECTION_KEYS, "correction binding"),
        (plan.get("seal"), SEAL_KEYS, "seal binding"),
        (plan.get("root_identity"), ROOT_IDENTITY_KEYS, "historical root identity"),
    )
    for value, keys, label in nested:
        _require(isinstance(value, dict) and set(value) == keys, f"{label} shape is invalid")
    anchors = plan.get("anchors")
    _require(isinstance(anchors, dict) and set(anchors) == {"current_task", "current_pack"}, "plan anchor shape is invalid")
    for label in ("current_task", "current_pack"):
        anchor = anchors[label]
        _require(isinstance(anchor, dict) and set(anchor) == ANCHOR_KEYS, f"{label} anchor shape is invalid")
        _require(
            isinstance(anchor.get("id"), str) and anchor["id"]
            and isinstance(anchor.get("path"), str) and anchor["path"]
            and _is_sha256(anchor.get("sha256")),
            f"{label} anchor is malformed",
        )
    root_identity = plan["root_identity"]
    _require(
        isinstance(root_identity.get("resolved_path"), str)
        and _is_int(root_identity.get("device"))
        and _is_int(root_identity.get("inode")),
        "historical root identity is malformed",
    )
    source = plan["source_prefix"]
    _require(
        _is_sha256(source.get("sha256"))
        and _is_int(source.get("byte_length")) and source["byte_length"] >= 0
        and _is_int(source.get("raw_row_count")) and source["raw_row_count"] >= 0,
        "source prefix scalar contract is invalid",
    )
    mapping = plan["mapping_manifest"]
    _require(
        _is_sha256(mapping.get("sha256"))
        and _is_int(mapping.get("schema_version"))
        and mapping["schema_version"] == 1,
        "mapping binding scalar contract is invalid",
    )
    _require(_is_sha256(plan["resolution_manifest"].get("sha256")), "resolution binding hash is invalid")
    correction = plan["correction_suffix"]
    _require(
        _is_sha256(correction.get("sha256"))
        and all(_is_int(correction.get(field)) and correction[field] >= 0 for field in ("byte_length", "event_count", "offset")),
        "correction binding scalar contract is invalid",
    )
    seal = plan["seal"]
    _require(
        _is_sha256(seal.get("line_sha256"))
        and _is_int(seal.get("offset")) and seal["offset"] >= 0
        and _is_int(seal.get("byte_length")) and seal["byte_length"] > 0
        and isinstance(seal.get("event"), dict),
        "seal binding scalar contract is invalid",
    )
    _require(
        _is_sha256(plan.get("expected_after_index_sha256"))
        and _is_int(plan.get("expected_commit_boundary_byte_length"))
        and plan["expected_commit_boundary_byte_length"] > 0
        and _is_sha256(plan.get("plan_contract_sha256")),
        "plan boundary scalar contract is invalid",
    )
    counts = plan.get("classification_counts")
    _require(
        isinstance(counts, dict)
        and set(counts) == {
            "accepted_current", "normalized_legacy", "mapped_legacy",
            "quarantined_historical", "blocked_unknown_or_future",
        }
        and all(_is_int(value) and value >= 0 for value in counts.values())
        and _is_int(plan.get("unclassified_count")) and plan["unclassified_count"] >= 0,
        "plan classification scalar contract is invalid",
    )


def _rebuild_plan(bundle: dict[str, Any], mapping: dict[str, Any], mapping_payload: bytes) -> dict[str, Any]:
    plan = bundle["plan"]
    _validate_plan_shapes(plan)
    transaction_id = bundle["transaction_id"]
    _require(plan.get("migration_id") == transaction_id, "plan transaction identity mismatch")
    prefix = bundle["refs"]["source_prefix"][1]
    source = plan["source_prefix"]
    _require(
        source == {
            "ref": ".task/index.jsonl",
            "sha256": _sha256(prefix),
            "byte_length": len(prefix),
            "raw_row_count": len(_physical_lines(prefix)),
        },
        "plan source prefix binding mismatch",
    )
    mapping_binding = plan["mapping_manifest"]
    _require(
        mapping_binding.get("sha256") == _sha256(mapping_payload)
        and mapping_binding.get("schema_version") == mapping["schema_version"]
        and mapping_binding.get("mapping_policy_id") == mapping["mapping_policy_id"]
        and mapping_binding.get("snapshot_ref") == bundle["receipt"]["mapping_manifest_ref"]
        and isinstance(mapping_binding.get("source_ref"), str)
        and bool(mapping_binding["source_ref"]),
        "plan mapping binding mismatch",
    )
    task_anchor, pack_anchor = plan["anchors"]["current_task"], plan["anchors"]["current_pack"]
    seed = {
        "source_sha256": _sha256(prefix),
        "mapping_sha256": _sha256(mapping_payload),
        "current_task_id": task_anchor["id"],
        "current_task_sha256": task_anchor["sha256"],
        "current_pack_id": pack_anchor["id"],
        "current_pack_sha256": pack_anchor["sha256"],
    }
    _require(
        transaction_id == "tsm-" + _sha256(_canonical_json(seed))[:24],
        "transaction identity is not independently reproducible",
    )
    rows, normalized, counts = _classify_prefix(prefix, mapping)
    corrections, projection = _make_corrections(
        normalized, mapping, transaction_id, task_anchor, pack_anchor
    )
    _bind_quarantine_corrections(rows, corrections, task_anchor["id"], pack_anchor["id"])
    _validate_quarantine_bindings(rows, corrections)
    manifest = _manifest(transaction_id, prefix, rows, counts)
    manifest_payload = _canonical_json(manifest)
    resolution_path = bundle["refs"]["resolution_manifest"][0]
    resolution_sha = _sha256_path(resolution_path)
    matches = resolution_path.stat().st_size == len(manifest_payload)
    if matches:
        view = memoryview(manifest_payload)
        offset = 0
        with resolution_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                if chunk != view[offset:offset + len(chunk)]:
                    matches = False
                    break
                offset += len(chunk)
        matches = matches and offset == len(manifest_payload)
    _require(
        matches,
        "resolution manifest differs from independent row reconstruction",
    )
    tx_ref = f".task/migrations/{transaction_id}"
    core = {
        "schema_version": 2,
        "kind": "task_state_index_migration_plan",
        "tool_version": plan["tool_version"],
        "migration_id": transaction_id,
        "root_identity": plan["root_identity"],
        "source_prefix": source,
        "mapping_manifest": mapping_binding,
        "resolution_manifest": {"ref": f"{tx_ref}/resolution-manifest.json", "sha256": _sha256(manifest_payload)},
        "source_snapshot_ref": f"{tx_ref}/legacy-prefix.jsonl",
        "plan_snapshot_ref": f"{tx_ref}/plan.json",
        "classification_counts": counts,
        "unclassified_count": counts["blocked_unknown_or_future"],
        "rows": rows,
        "correction_events": corrections,
        "projection": projection,
        "anchors": {"current_task": task_anchor, "current_pack": pack_anchor},
        "effective_at": mapping["effective_at"],
        "transaction_directory_ref": tx_ref,
        "historical_rows_removed": 0,
        "historical_rows_reordered": 0,
        "original_row_bytes_modified": 0,
        "prefix_preserved": True,
    }
    contract_sha = _sha256(_canonical_json(core))
    _require(plan.get("plan_contract_sha256") == contract_sha, "plan contract hash mismatch")
    joiner = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    correction_payload = joiner + _event_bytes(corrections)
    seal_id = f"schema-{transaction_id}-seal"
    seal_event = _versioned({
        "event": "upsert", "id": seal_id, "type": "schema_contract", "status": "informational",
        "path": f"{tx_ref}/receipt.json", "title": "Task state legacy migration seal",
        "updated_at": mapping["effective_at"],
        "fields": {
            MIGRATION_EVENT_FIELD: SEAL_KIND,
            "migration_id": transaction_id,
            "plan_contract_sha256": contract_sha,
            "source_prefix_sha256": _sha256(prefix),
            "source_prefix_byte_length": len(prefix),
            "source_raw_row_count": len(rows),
            "mapping_manifest_sha256": _sha256(mapping_payload),
            "resolution_manifest_sha256": _sha256(manifest_payload),
            "correction_suffix_sha256": _sha256(correction_payload),
            "correction_suffix_byte_length": len(correction_payload),
        },
    })
    seal_line = _canonical_json(seal_event)
    boundary_parts = (prefix, correction_payload, seal_line)
    boundary_digest = hashlib.sha256()
    for part in boundary_parts:
        boundary_digest.update(part)
    boundary_sha = boundary_digest.hexdigest()
    boundary_length = sum(len(part) for part in boundary_parts)
    expected = {
        **core,
        "plan_contract_sha256": contract_sha,
        "correction_suffix": {
            "ref": f"{tx_ref}/correction-suffix.jsonl", "sha256": _sha256(correction_payload),
            "byte_length": len(correction_payload), "event_count": len(corrections), "offset": len(prefix),
        },
        "seal": {"id": seal_id, "event": seal_event, "line_sha256": _sha256(seal_line),
                 "offset": len(prefix) + len(correction_payload), "byte_length": len(seal_line)},
        "expected_after_index_sha256": boundary_sha,
        "expected_commit_boundary_byte_length": boundary_length,
        "receipt_ref": f"{tx_ref}/receipt.json",
        "receipt_anchor_id": seal_id,
        "journal_ref": f"{tx_ref}/journal.json",
        "prepare_journal_ref": f"{tx_ref}/journal-prepare.json",
        "completion_marker_ref": f"{tx_ref}/journal-completion.json",
        "render_snapshot_ref": f"{tx_ref}/rendered-index.md",
    }
    _require(plan == expected, "plan differs from independent reconstruction")
    bundle["plan"] = expected
    _require(bundle["refs"]["correction_suffix"][1] == correction_payload, "correction suffix bytes mismatch")
    _require(counts["blocked_unknown_or_future"] == 0, "committed plan contains blocked prefix rows")
    return {"plan": expected, "prefix": prefix, "normalized": normalized, "rows": rows,
            "counts": counts, "corrections": corrections, "projection": projection,
            "manifest": manifest, "resolution_manifest_sha256": resolution_sha,
            "boundary_parts": boundary_parts, "seal_line": seal_line}


def _prepare_document(plan: dict[str, Any], plan_sha: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "task_state_index_migration_journal_prepare",
        "transaction_id": plan["migration_id"],
        "state": "prepared",
        "prefix_sha256": plan["source_prefix"]["sha256"],
        "prefix_byte_length": plan["source_prefix"]["byte_length"],
        "expected_boundary_sha256": plan["expected_after_index_sha256"],
        "expected_boundary_byte_length": plan["expected_commit_boundary_byte_length"],
        "plan_ref": plan["plan_snapshot_ref"],
        "plan_sha256": plan_sha,
    }


def _journal_document(
    prepare: dict[str, Any], plan: dict[str, Any], committed_at: str, render_sha: str, recovery_status: str
) -> dict[str, Any]:
    return {
        **prepare,
        "kind": "task_state_index_migration_journal",
        "state": "committed",
        "journal_updated_at": committed_at,
        "receipt_ref": plan["receipt_ref"],
        "seal_sha256": plan["seal"]["line_sha256"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "rendered_index_ref": plan["render_snapshot_ref"],
        "rendered_index_sha256": render_sha,
        "recovery_status": recovery_status,
    }


def _marker_document(
    plan: dict[str, Any], prepare_sha: str, journal_sha: str, render_sha: str,
    recovery_status: str, committed_at: str, plan_sha: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1, "kind": "task_state_index_migration_completion_marker",
        "transaction_id": plan["migration_id"], "state": "committed", "committed_at": committed_at,
        "prepare_journal_ref": plan["prepare_journal_ref"], "prepare_journal_sha256": prepare_sha,
        "journal_ref": plan["journal_ref"], "journal_sha256": journal_sha,
        "receipt_ref": plan["receipt_ref"], "plan_ref": plan["plan_snapshot_ref"],
        "plan_sha256": plan_sha, "seal_sha256": plan["seal"]["line_sha256"],
        "commit_boundary_length": plan["expected_commit_boundary_byte_length"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "rendered_index_ref": plan["render_snapshot_ref"], "rendered_index_sha256": render_sha,
        "recovery_status": recovery_status,
    }


def _receipt_document(
    plan: dict[str, Any], rebuilt: dict[str, Any], plan_sha: str, prepare_sha: str,
    journal_sha: str, marker_sha: str, render_sha: str, recovery_status: str, committed_at: str,
) -> dict[str, Any]:
    counts, projection = rebuilt["counts"], rebuilt["projection"]
    return {
        "schema_version": 2, "kind": "task_state_index_migration", "transaction_id": plan["migration_id"],
        "tool_version": plan["tool_version"], "transaction_started_at": committed_at,
        "transaction_committed_at": committed_at, "status": "committed",
        "source_prefix_ref": plan["source_snapshot_ref"], "source_prefix_sha256": plan["source_prefix"]["sha256"],
        "source_prefix_byte_length": plan["source_prefix"]["byte_length"], "source_raw_row_count": plan["source_prefix"]["raw_row_count"],
        "accepted_current_count": counts["accepted_current"], "normalized_legacy_count": counts["normalized_legacy"],
        "mapped_legacy_count": counts["mapped_legacy"], "quarantined_historical_count": counts["quarantined_historical"],
        "blocked_count": counts["blocked_unknown_or_future"], "mapping_manifest_ref": plan["mapping_manifest"]["snapshot_ref"],
        "mapping_manifest_sha256": plan["mapping_manifest"]["sha256"], "resolution_manifest_ref": plan["resolution_manifest"]["ref"],
        "resolution_manifest_sha256": plan["resolution_manifest"]["sha256"], "plan_ref": plan["plan_snapshot_ref"],
        "plan_sha256": plan_sha, "plan_contract_sha256": plan["plan_contract_sha256"],
        "correction_suffix_ref": plan["correction_suffix"]["ref"], "correction_suffix_sha256": plan["correction_suffix"]["sha256"],
        "correction_suffix_byte_length": plan["correction_suffix"]["byte_length"], "correction_suffix_count": plan["correction_suffix"]["event_count"],
        "correction_suffix_offset": plan["correction_suffix"]["offset"], "seal_id": plan["seal"]["id"],
        "seal_sha256": plan["seal"]["line_sha256"], "seal_offset": plan["seal"]["offset"],
        "seal_byte_length": plan["seal"]["byte_length"], "commit_boundary_length": plan["expected_commit_boundary_byte_length"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"], "prefix_preserved": True,
        "historical_rows_removed": 0, "historical_rows_reordered": 0, "original_row_bytes_modified": 0,
        "canonical_task": plan["anchors"]["current_task"], "canonical_pack": plan["anchors"]["current_pack"],
        "superseded_task_id_digest": _sha256(_canonical_json(projection["superseded_task_ids"])),
        "superseded_pack_id_digest": _sha256(_canonical_json(projection["superseded_pack_ids"])),
        "retracted_link_pair_digest": _sha256(_canonical_json(projection["retracted_links"])),
        "active_task_count": projection["active_task_count"], "active_pack_count": projection["active_pack_count"],
        "duplicate_active_alias_count": projection["duplicate_active_alias_count"], "current_broken_link_count": projection["current_broken_link_count"],
        "before_active_task_count": projection["before_active_task_count"], "before_active_pack_count": projection["before_active_pack_count"],
        "before_duplicate_active_alias_count": projection["before_duplicate_active_alias_count"],
        "before_current_broken_link_count": projection["before_current_broken_link_count"],
        "current_active_pack_indexed": projection["current_active_pack_indexed"],
        "current_projection_status": projection["current_projection_status"], "projection_completeness": projection["projection_completeness"],
        "current_surface_blocker_count": projection["current_surface_blocker_count"], "strict_reader_status": "pass",
        "append_simulation_status": "pass", "audit_status": "current_projection_pass_historical_debt_preserved",
        "rendered_index_ref": plan["render_snapshot_ref"], "rendered_index_sha256": render_sha,
        "prepare_journal_ref": plan["prepare_journal_ref"], "prepare_journal_sha256": prepare_sha,
        "journal_ref": plan["journal_ref"], "journal_sha256": journal_sha,
        "completion_marker_ref": plan["completion_marker_ref"], "completion_marker_sha256": marker_sha,
        "recovery_status": recovery_status,
    }


def _verify_publication(
    bundle: dict[str, Any], rebuilt: dict[str, Any], expected_recovery_status: str
) -> dict[str, Any]:
    _require(expected_recovery_status in {"not_required", "forward_completed"}, "caller recovery expectation is invalid")
    plan, receipt = rebuilt["plan"], bundle["receipt"]
    publication_recovery_status = receipt.get("recovery_status")
    _require(
        publication_recovery_status in {"not_required", "forward_completed"},
        "receipt recovery state is invalid",
    )
    plan_sha = bundle["plan_sha256"]
    prepare = _prepare_document(plan, plan_sha)
    prepare_payload = _canonical_json(prepare)
    _require(set(bundle["prepare_journal"]) == PREPARE_KEYS and bundle["refs"]["prepare_journal"][1] == prepare_payload, "prepare journal differs from independent reconstruction")
    placeholder = _anchor_event(plan, "0" * 64, "0" * 64, "0" * 64)
    rendered = _render_markdown(rebuilt["normalized"] + rebuilt["corrections"] + [plan["seal"]["event"], placeholder], plan["effective_at"])
    _require(bundle["refs"]["rendered_index"][1] == rendered, "rendered migration snapshot differs from independent projection")
    render_sha = _sha256(rendered)
    committed_at = receipt.get("transaction_committed_at")
    _require(isinstance(committed_at, str) and committed_at and receipt.get("transaction_started_at") == committed_at, "receipt completion time is malformed")
    journal = _journal_document(
        prepare, plan, committed_at, render_sha, publication_recovery_status,
    )
    journal_payload = _canonical_json(journal)
    _require(set(bundle["journal"]) == JOURNAL_KEYS and bundle["refs"]["journal"][1] == journal_payload, "committed journal differs from independent reconstruction")
    marker = _marker_document(
        plan, _sha256(prepare_payload), _sha256(journal_payload), render_sha,
        publication_recovery_status, committed_at, plan_sha,
    )
    marker_payload = _canonical_json(marker)
    _require(set(bundle["completion_marker"]) == MARKER_KEYS and bundle["refs"]["completion_marker"][1] == marker_payload, "completion marker differs from independent reconstruction")
    expected_receipt = _receipt_document(
        plan, rebuilt, plan_sha, _sha256(prepare_payload), _sha256(journal_payload),
        _sha256(marker_payload), render_sha, publication_recovery_status,
        committed_at,
    )
    _require(receipt == expected_receipt and bundle["receipt_payload"] == _canonical_json(expected_receipt), "receipt differs from independent reconstruction")
    return {"prepare_sha": _sha256(prepare_payload), "journal_sha": _sha256(journal_payload),
            "marker_sha": _sha256(marker_payload), "render_sha": render_sha,
            "receipt_sha": _sha256(bundle["receipt_payload"]), "plan_sha": plan_sha,
            "recovery_status": publication_recovery_status}


def _phase_receipt_sha256(
    rebuilt: dict[str, Any],
    publication: dict[str, Any],
    observation: dict[str, Any] | None,
) -> str | None:
    if not isinstance(observation, dict) or not observation.get("receipt_present"):
        return None
    recovery_status = observation.get("receipt_recovery_status")
    committed_at = observation.get("receipt_committed_at")
    _require(
        recovery_status in {"not_required", "forward_completed"}
        and isinstance(committed_at, str)
        and bool(committed_at),
        "pre-recovery receipt identity is invalid",
    )
    plan = rebuilt["plan"]
    plan_sha = publication["plan_sha"]
    render_sha = publication["render_sha"]
    prepare = _prepare_document(plan, plan_sha)
    prepare_sha = _sha256(_canonical_json(prepare))
    journal = _journal_document(
        prepare, plan, committed_at, render_sha, recovery_status,
    )
    journal_sha = _sha256(_canonical_json(journal))
    marker = _marker_document(
        plan, prepare_sha, journal_sha, render_sha, recovery_status,
        committed_at, plan_sha,
    )
    receipt = _receipt_document(
        plan, rebuilt, plan_sha, prepare_sha, journal_sha,
        _sha256(_canonical_json(marker)), render_sha, recovery_status,
        committed_at,
    )
    return _sha256(_canonical_json(receipt))


def _parse_current_ledger(
    bundle: dict[str, Any], rebuilt: dict[str, Any], publication: dict[str, Any]
) -> dict[str, Any]:
    root, plan = bundle["root"], rebuilt["plan"]
    ledger_path = _regular_file(root / ".task" / "index.jsonl", "current task-state index")
    boundary_length = plan["expected_commit_boundary_byte_length"]
    anchor = _anchor_event(plan, publication["receipt_sha"], publication["journal_sha"], publication["marker_sha"])
    anchor_line = _canonical_json(anchor)
    _require(boundary_length == bundle["receipt"]["commit_boundary_length"], "receipt anchor offset differs from commit boundary length")
    known_ids = {event["id"] for event in rebuilt["normalized"] if isinstance(event.get("id"), str) and event["id"]}
    sealed_events = rebuilt["corrections"] + [plan["seal"]["event"], anchor]
    state = _merge_state(rebuilt["normalized"])
    for event in sealed_events:
        _validate_suffix_event(event, known_ids)
        _merge_event_into_state(state, event)
    event_count = len(rebuilt["normalized"]) + len(sealed_events)
    post_anchor_lines = 0
    digest = hashlib.sha256()
    with ledger_path.open("rb") as handle:
        for part in rebuilt["boundary_parts"]:
            view = memoryview(part)
            offset = 0
            while offset < len(part):
                chunk = handle.read(min(1024 * 1024, len(part) - offset))
                _require(chunk == view[offset:offset + len(chunk)] and chunk, "current ledger historical commit boundary mismatch")
                digest.update(chunk)
                offset += len(chunk)
        observed_anchor = handle.read(len(anchor_line))
        _require(observed_anchor == anchor_line, "receipt anchor is not located exactly at the commit boundary")
        digest.update(observed_anchor)
        for raw in handle:
            digest.update(raw)
            post_anchor_lines += 1
            if not raw.strip():
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise VerificationError(f"post-anchor ledger row is malformed: {exc}") from exc
            _require(isinstance(event, dict), "post-anchor ledger row is not an object")
            _validate_suffix_event(event, known_ids)
            _merge_event_into_state(state, event)
            event_count += 1
    current_projection, current_identities = _current_projection(state, root)
    historical_basis = {
        "transaction_id": plan["migration_id"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "canonical_task": plan["anchors"]["current_task"],
        "canonical_pack": plan["anchors"]["current_pack"],
        "projection": rebuilt["projection"],
    }
    current_basis = {
        "task": current_identities["task"],
        "pack": current_identities["pack"],
        "projection": current_projection,
    }
    return {
        "ledger_sha256": digest.hexdigest(),
        "historical_boundary_task_id": plan["anchors"]["current_task"]["id"],
        "historical_boundary_pack_id": plan["anchors"]["current_pack"]["id"],
        "historical_boundary_evidence_ref": f"{bundle['receipt']['plan_ref']}#anchors",
        "historical_boundary_identity_sha256": _sha256(_canonical_json(historical_basis)),
        "post_migration_current_task_id": current_identities["task"]["id"],
        "post_migration_current_pack_id": current_identities["pack"]["id"],
        "post_migration_current_evidence_ref": ".task/index.jsonl#post_anchor_projection",
        "post_migration_current_identity_sha256": _sha256(_canonical_json(current_basis)),
        "post_anchor_event_count": post_anchor_lines,
        "current_event_count": event_count,
        "anchor_sha256": _sha256(anchor_line),
    }


def verify_migration(
    root_raw: str | Path,
    receipt_raw: str | Path,
    *,
    expected_mapping_raw: str | Path,
    expected_recovery_status: str,
    recovery_observation: dict[str, Any] | None = None,
    expected_recovery_observation_sha256: str | None = None,
) -> dict[str, Any]:
    """Verify a committed graph without importing or executing producer code."""
    bundle = _load_bundle(root_raw, receipt_raw)
    mapping, mapping_payload, _mapping_path = _external_mapping(bundle, expected_mapping_raw)
    rebuilt = _rebuild_plan(bundle, mapping, mapping_payload)
    publication = _verify_publication(bundle, rebuilt, expected_recovery_status)
    current = _parse_current_ledger(bundle, rebuilt, publication)
    phase_receipt_sha = _phase_receipt_sha256(
        rebuilt, publication, recovery_observation,
    )
    recovery = verify_recovery_observation(
        bundle, rebuilt, publication, current, expected_recovery_status,
        recovery_observation, expected_recovery_observation_sha256,
        phase_receipt_sha,
    )
    recovery_phase = (
        recovery_observation["journal_state"]
        if isinstance(recovery_observation, dict)
        else "not_applicable"
    )
    recovery_publication_state = (
        recovery_observation["publication_state"]
        if isinstance(recovery_observation, dict)
        else "not_applicable"
    )
    fixed_graph_basis = {
        "transaction_id": bundle["transaction_id"],
        "source_prefix_sha256": _sha256(rebuilt["prefix"]),
        "mapping_manifest_sha256": _sha256(mapping_payload),
        "resolution_manifest_sha256": rebuilt["resolution_manifest_sha256"],
        "plan_sha256": bundle["plan_sha256"],
        "correction_suffix_sha256": _sha256(bundle["refs"]["correction_suffix"][1]),
        "seal_sha256": rebuilt["plan"]["seal"]["line_sha256"],
        "receipt_sha256": publication["receipt_sha"],
        "journal_sha256": publication["journal_sha"],
        "completion_marker_sha256": publication["marker_sha"],
        "anchor_sha256": current["anchor_sha256"],
        "commit_boundary_sha256": rebuilt["plan"]["expected_after_index_sha256"],
        "caller_recovery_status": expected_recovery_status,
        "publication_recovery_status": publication["recovery_status"],
        "recovery_phase": recovery_phase,
        "recovery_publication_state": recovery_publication_state,
        "historical_boundary_identity_sha256": current["historical_boundary_identity_sha256"],
        "post_migration_current_identity_sha256": current["post_migration_current_identity_sha256"],
        "operation_scope": "verifier_process",
    }
    if recovery["observation_sha"] is not None:
        fixed_graph_basis["recovery_observation_sha256"] = recovery["observation_sha"]
    if phase_receipt_sha is not None:
        fixed_graph_basis["pre_recovery_receipt_sha256"] = phase_receipt_sha
    return {
        "schema_version": 1,
        "kind": "task_state_migration_independent_verification",
        "status": "pass",
        "evaluation_status": "pass",
        "verifier": "task_state_migration_sealed_reader_recovery_boundary_independent_verifier",
        "source_separated": True,
        "read_only": True,
        "transaction_id": bundle["transaction_id"],
        "recovery_status": expected_recovery_status,
        "publication_recovery_status": publication["recovery_status"],
        "recovery_observation_phase": recovery_phase,
        "recovery_publication_state": recovery_publication_state,
        "expected_mapping_sha256": _sha256(mapping_payload),
        "source_raw_row_count": len(rebuilt["rows"]),
        "correction_suffix_count": len(rebuilt["corrections"]),
        "current_event_count": current["current_event_count"],
        "post_anchor_event_count": current["post_anchor_event_count"],
        "historical_boundary_task_id": _opaque_identity_token(
            current["historical_boundary_task_id"], "task",
        ),
        "historical_boundary_pack_id": _opaque_identity_token(
            current["historical_boundary_pack_id"], "pack",
        ),
        "historical_boundary_evidence_ref": current["historical_boundary_evidence_ref"],
        "historical_boundary_identity_sha256": current["historical_boundary_identity_sha256"],
        "migration_boundary_evidence_sha256": rebuilt["plan"]["expected_after_index_sha256"],
        "post_migration_current_task_id": _opaque_identity_token(
            current["post_migration_current_task_id"], "task",
        ),
        "post_migration_current_pack_id": _opaque_identity_token(
            current["post_migration_current_pack_id"], "pack",
        ),
        "post_migration_current_evidence_ref": current["post_migration_current_evidence_ref"],
        "post_migration_current_identity_sha256": current["post_migration_current_identity_sha256"],
        "post_migration_current_evidence_sha256": current["ledger_sha256"],
        "recovery_owned_write_set_sha256": _owned_write_set_sha(recovery["owned"]),
        "recovery_owned_write_path_count": len(recovery["owned"]),
        "outside_owned_tree_sha256": recovery["outside_sha"],
        "graph_sha256": _sha256(_canonical_json(fixed_graph_basis)),
        "operation_scope": "verifier_process",
        "verifier_migration_apply_count": 0,
        "verifier_migration_recover_count": 0,
        "verifier_migration_replay_count": 0,
        "semantic_progress": False,
        "artifact_truth_completion": False,
        "issue_state_evaluation": "external_cycle_evidence_required",
    }
