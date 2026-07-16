"""Validate and independently reconstruct an immutable migration plan."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from .core import (
    MIGRATION_EVENT_FIELD,
    SEAL_KIND,
    TOOL_VERSIONS,
    _canonical_json,
    _event_bytes,
    _is_int,
    _is_sha256,
    _physical_lines,
    _require,
    _sha256,
    _sha256_path,
    _versioned,
)
from .correction_evidence import (
    _bind_quarantine_corrections,
    _make_corrections,
    _manifest,
    _validate_quarantine_bindings,
)
from .graph_contracts import (
    ANCHOR_KEYS,
    CORRECTION_KEYS,
    MAPPING_BINDING_KEYS,
    PLAN_KEYS,
    REF_SHA_KEYS,
    ROOT_IDENTITY_KEYS,
    SEAL_KEYS,
    SOURCE_PREFIX_KEYS,
)
from .mapping_evidence import _classify_prefix


@dataclass(frozen=True)
class RebuildContext:
    bundle: dict[str, Any]
    plan: dict[str, Any]
    transaction_id: str
    prefix: bytes
    source: dict[str, Any]
    mapping_binding: dict[str, Any]
    task_anchor: dict[str, Any]
    pack_anchor: dict[str, Any]


@dataclass(frozen=True)
class RebuildEvidence:
    rows: list[dict[str, Any]]
    normalized: list[dict[str, Any]]
    counts: dict[str, int]
    corrections: list[dict[str, Any]]
    projection: dict[str, Any]
    manifest: dict[str, Any]
    manifest_payload: bytes
    resolution_manifest_sha256: str


@dataclass(frozen=True)
class SealProjection:
    contract_sha: str
    correction_payload: bytes
    seal_id: str
    seal_event: dict[str, Any]
    seal_line: bytes
    boundary_parts: tuple[bytes, bytes, bytes]
    boundary_sha: str
    boundary_length: int

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

def _load_rebuild_context(
    bundle: dict[str, Any], mapping: dict[str, Any], mapping_payload: bytes
) -> RebuildContext:
    plan = bundle["plan"]
    _validate_plan_shapes(plan)
    transaction_id = bundle["transaction_id"]
    _require(
        plan.get("migration_id") == transaction_id,
        "plan transaction identity mismatch",
    )
    prefix = bundle["refs"]["source_prefix"][1]
    source = plan["source_prefix"]
    _require(
        source
        == {
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
        and mapping_binding.get("mapping_policy_id")
        == mapping["mapping_policy_id"]
        and mapping_binding.get("snapshot_ref")
        == bundle["receipt"]["mapping_manifest_ref"]
        and isinstance(mapping_binding.get("source_ref"), str)
        and bool(mapping_binding["source_ref"]),
        "plan mapping binding mismatch",
    )
    task_anchor = plan["anchors"]["current_task"]
    pack_anchor = plan["anchors"]["current_pack"]
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
    return RebuildContext(
        bundle=bundle,
        plan=plan,
        transaction_id=transaction_id,
        prefix=prefix,
        source=source,
        mapping_binding=mapping_binding,
        task_anchor=task_anchor,
        pack_anchor=pack_anchor,
    )


def _verify_resolution_manifest(
    context: RebuildContext, manifest_payload: bytes
) -> str:
    resolution_path = context.bundle["refs"]["resolution_manifest"][0]
    resolution_sha = _sha256_path(resolution_path)
    matches = resolution_path.stat().st_size == len(manifest_payload)
    if matches:
        view = memoryview(manifest_payload)
        offset = 0
        with resolution_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                if chunk != view[offset : offset + len(chunk)]:
                    matches = False
                    break
                offset += len(chunk)
        matches = matches and offset == len(manifest_payload)
    _require(
        matches,
        "resolution manifest differs from independent row reconstruction",
    )
    return resolution_sha


def _rebuild_evidence(
    context: RebuildContext, mapping: dict[str, Any]
) -> RebuildEvidence:
    rows, normalized, counts = _classify_prefix(context.prefix, mapping)
    corrections, projection = _make_corrections(
        normalized,
        mapping,
        context.transaction_id,
        context.task_anchor,
        context.pack_anchor,
    )
    _bind_quarantine_corrections(
        rows,
        corrections,
        context.task_anchor["id"],
        context.pack_anchor["id"],
    )
    _validate_quarantine_bindings(rows, corrections)
    manifest = _manifest(
        context.transaction_id, context.prefix, rows, counts
    )
    manifest_payload = _canonical_json(manifest)
    resolution_sha = _verify_resolution_manifest(context, manifest_payload)
    return RebuildEvidence(
        rows=rows,
        normalized=normalized,
        counts=counts,
        corrections=corrections,
        projection=projection,
        manifest=manifest,
        manifest_payload=manifest_payload,
        resolution_manifest_sha256=resolution_sha,
    )


def _build_core(
    context: RebuildContext,
    evidence: RebuildEvidence,
    mapping: dict[str, Any],
) -> dict[str, Any]:
    tx_ref = f".task/migrations/{context.transaction_id}"
    return {
        "schema_version": 2,
        "kind": "task_state_index_migration_plan",
        "tool_version": context.plan["tool_version"],
        "migration_id": context.transaction_id,
        "root_identity": context.plan["root_identity"],
        "source_prefix": context.source,
        "mapping_manifest": context.mapping_binding,
        "resolution_manifest": {
            "ref": f"{tx_ref}/resolution-manifest.json",
            "sha256": _sha256(evidence.manifest_payload),
        },
        "source_snapshot_ref": f"{tx_ref}/legacy-prefix.jsonl",
        "plan_snapshot_ref": f"{tx_ref}/plan.json",
        "classification_counts": evidence.counts,
        "unclassified_count": evidence.counts["blocked_unknown_or_future"],
        "rows": evidence.rows,
        "correction_events": evidence.corrections,
        "projection": evidence.projection,
        "anchors": {
            "current_task": context.task_anchor,
            "current_pack": context.pack_anchor,
        },
        "effective_at": mapping["effective_at"],
        "transaction_directory_ref": tx_ref,
        "historical_rows_removed": 0,
        "historical_rows_reordered": 0,
        "original_row_bytes_modified": 0,
        "prefix_preserved": True,
    }


def _build_seal(
    context: RebuildContext,
    evidence: RebuildEvidence,
    mapping: dict[str, Any],
    mapping_payload: bytes,
    core: dict[str, Any],
) -> SealProjection:
    contract_sha = _sha256(_canonical_json(core))
    _require(
        context.plan.get("plan_contract_sha256") == contract_sha,
        "plan contract hash mismatch",
    )
    joiner = b"\n" if context.prefix and not context.prefix.endswith(b"\n") else b""
    correction_payload = joiner + _event_bytes(evidence.corrections)
    seal_id = f"schema-{context.transaction_id}-seal"
    tx_ref = f".task/migrations/{context.transaction_id}"
    seal_event = _versioned(
        {
            "event": "upsert",
            "id": seal_id,
            "type": "schema_contract",
            "status": "informational",
            "path": f"{tx_ref}/receipt.json",
            "title": "Task state legacy migration seal",
            "updated_at": mapping["effective_at"],
            "fields": {
                MIGRATION_EVENT_FIELD: SEAL_KIND,
                "migration_id": context.transaction_id,
                "plan_contract_sha256": contract_sha,
                "source_prefix_sha256": _sha256(context.prefix),
                "source_prefix_byte_length": len(context.prefix),
                "source_raw_row_count": len(evidence.rows),
                "mapping_manifest_sha256": _sha256(mapping_payload),
                "resolution_manifest_sha256": _sha256(evidence.manifest_payload),
                "correction_suffix_sha256": _sha256(correction_payload),
                "correction_suffix_byte_length": len(correction_payload),
            },
        }
    )
    seal_line = _canonical_json(seal_event)
    boundary_parts = (context.prefix, correction_payload, seal_line)
    boundary_digest = hashlib.sha256()
    for part in boundary_parts:
        boundary_digest.update(part)
    return SealProjection(
        contract_sha=contract_sha,
        correction_payload=correction_payload,
        seal_id=seal_id,
        seal_event=seal_event,
        seal_line=seal_line,
        boundary_parts=boundary_parts,
        boundary_sha=boundary_digest.hexdigest(),
        boundary_length=sum(len(part) for part in boundary_parts),
    )


def _build_expected_plan(
    context: RebuildContext,
    evidence: RebuildEvidence,
    core: dict[str, Any],
    seal: SealProjection,
) -> dict[str, Any]:
    tx_ref = f".task/migrations/{context.transaction_id}"
    return {
        **core,
        "plan_contract_sha256": seal.contract_sha,
        "correction_suffix": {
            "ref": f"{tx_ref}/correction-suffix.jsonl",
            "sha256": _sha256(seal.correction_payload),
            "byte_length": len(seal.correction_payload),
            "event_count": len(evidence.corrections),
            "offset": len(context.prefix),
        },
        "seal": {
            "id": seal.seal_id,
            "event": seal.seal_event,
            "line_sha256": _sha256(seal.seal_line),
            "offset": len(context.prefix) + len(seal.correction_payload),
            "byte_length": len(seal.seal_line),
        },
        "expected_after_index_sha256": seal.boundary_sha,
        "expected_commit_boundary_byte_length": seal.boundary_length,
        "receipt_ref": f"{tx_ref}/receipt.json",
        "receipt_anchor_id": seal.seal_id,
        "journal_ref": f"{tx_ref}/journal.json",
        "prepare_journal_ref": f"{tx_ref}/journal-prepare.json",
        "completion_marker_ref": f"{tx_ref}/journal-completion.json",
        "render_snapshot_ref": f"{tx_ref}/rendered-index.md",
    }


def _rebuild_plan(
    bundle: dict[str, Any], mapping: dict[str, Any], mapping_payload: bytes
) -> dict[str, Any]:
    context = _load_rebuild_context(bundle, mapping, mapping_payload)
    evidence = _rebuild_evidence(context, mapping)
    core = _build_core(context, evidence, mapping)
    seal = _build_seal(context, evidence, mapping, mapping_payload, core)
    expected = _build_expected_plan(context, evidence, core, seal)
    _require(
        context.plan == expected,
        "plan differs from independent reconstruction",
    )
    bundle["plan"] = expected
    _require(
        bundle["refs"]["correction_suffix"][1] == seal.correction_payload,
        "correction suffix bytes mismatch",
    )
    _require(
        evidence.counts["blocked_unknown_or_future"] == 0,
        "committed plan contains blocked prefix rows",
    )
    return {
        "plan": expected,
        "prefix": context.prefix,
        "normalized": evidence.normalized,
        "rows": evidence.rows,
        "counts": evidence.counts,
        "corrections": evidence.corrections,
        "projection": evidence.projection,
        "manifest": evidence.manifest,
        "resolution_manifest_sha256": evidence.resolution_manifest_sha256,
        "boundary_parts": seal.boundary_parts,
        "seal_line": seal.seal_line,
    }
