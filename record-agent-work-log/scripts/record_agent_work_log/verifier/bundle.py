"""Verification bundle loading and document header checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import (
    MIGRATION_KIND,
    VerificationError,
    _canonical_json,
    _hashed_ref,
    _is_int,
    _load_json,
    _migration_ref,
    _regular_file,
    _require,
    _root,
    _sha256,
)

from .graph_contracts import (
    JOURNAL_FORWARD_AFTER_COMMIT_KEYS,
    JOURNAL_FORWARD_KEYS,
    JOURNAL_KEYS,
    MANIFEST_KEYS,
    PLAN_KEYS,
    RECEIPT_KEYS,
)


def _load_verification_bundle(
    root_raw: str | Path, receipt_raw: str | Path
) -> dict[str, Any]:
    root = _root(root_raw)
    receipt_path = Path(receipt_raw)
    if not receipt_path.is_absolute():
        receipt_path = root / receipt_path
    try:
        receipt_relative = receipt_path.resolve(strict=True).relative_to(root).as_posix()
    except (OSError, ValueError) as exc:
        raise VerificationError("receipt must be a workspace-local regular file") from exc
    receipt_path = _regular_file(root / receipt_relative, "receipt")
    receipt, receipt_payload = _load_json(receipt_path, "receipt")
    _require(set(receipt) == RECEIPT_KEYS, "receipt is not the exact schema-v1 projection")
    migration_id = receipt.get("migration_id")
    _require(isinstance(migration_id, str) and migration_id, "receipt migration identity is missing")
    _require(
        _migration_ref(root, receipt_relative, migration_id, "receipt")
        == receipt_path,
        "receipt is outside its transaction",
    )
    _require(
        _is_int(receipt.get("schema_version"))
        and receipt["schema_version"] == 1
        and receipt.get("kind") == MIGRATION_KIND,
        "receipt schema or kind mismatch",
    )
    _require(
        receipt.get("transaction_status") == "committed",
        "producer success is not a committed receipt",
    )
    zero_fields = (
        "unresolved_count",
        "body_mutation_count",
        "missing_body_count",
        "post_legacy_count",
        "post_orphan_count",
        "post_duplicate_count",
    )
    for field in zero_fields:
        _require(
            _is_int(receipt.get(field)) and receipt[field] == 0,
            f"receipt {field} is not zero",
        )
    _require(
        receipt.get("historical_claims_upgraded") is False,
        "receipt upgrades historical claims",
    )
    _require(
        receipt.get("post_integrity_status") == "valid"
        and receipt.get("appendability_status") == "pass",
        "receipt publication claims are incomplete",
    )
    refs: dict[str, tuple[Path, bytes]] = {}
    for name, ref_field, sha_field in (
        ("source", "source_snapshot_ref", "source_snapshot_sha256"),
        ("plan", "plan_ref", "plan_sha256"),
        ("status", "status_map_ref", "status_map_sha256"),
        ("manifest", "resolution_manifest_ref", "resolution_manifest_sha256"),
    ):
        refs[name] = _hashed_ref(
            root,
            receipt,
            ref_field,
            sha_field,
            migration_id,
            name,
        )
    journal_path = _migration_ref(
        root, receipt.get("journal_ref"), migration_id, "journal"
    )
    staged_path = _migration_ref(
        root,
        f".agent_log/migrations/{migration_id}/staged-index.snapshot",
        migration_id,
        "staged index",
    )
    documents = {
        "plan": _load_json(refs["plan"][0], "plan")[0],
        "status": _load_json(refs["status"][0], "status map")[0],
        "manifest": _load_json(refs["manifest"][0], "resolution manifest")[0],
        "journal": _load_json(journal_path, "journal")[0],
    }
    journal_payload = journal_path.read_bytes()
    return {
        "root": root,
        "receipt_path": receipt_path,
        "receipt_relative": receipt_relative,
        "receipt": receipt,
        "receipt_payload": receipt_payload,
        "migration_id": migration_id,
        "refs": refs,
        "journal_path": journal_path,
        "journal_payload": journal_payload,
        "staged_path": staged_path,
        **documents,
    }

def _verify_document_headers(
    bundle: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    migration_id = bundle["migration_id"]
    plan = bundle["plan"]
    manifest = bundle["manifest"]
    journal = bundle["journal"]
    for document, label in (
        (plan, "plan"),
        (manifest, "manifest"),
        (journal, "journal"),
    ):
        _require(
            document.get("migration_id") == migration_id,
            f"{label} migration identity mismatch",
        )
        _require(
            _is_int(document.get("schema_version"))
            and document["schema_version"] == 1,
            f"{label} schema mismatch",
        )
    _require(set(plan) == PLAN_KEYS, "plan is not the exact schema-v1 projection")
    _require(
        set(manifest) == MANIFEST_KEYS,
        "manifest is not the exact schema-v1 projection",
    )
    if journal.get("recovery_status") == "forward_completed":
        journal_key_match = frozenset(journal) in {
            JOURNAL_FORWARD_KEYS,
            JOURNAL_FORWARD_AFTER_COMMIT_KEYS,
        }
    else:
        journal_key_match = set(journal) == JOURNAL_KEYS
    _require(journal_key_match, "journal is not the exact schema-v1 projection")
    _require(
        manifest.get("kind") == "agent_log_migration_resolution_manifest",
        "manifest kind mismatch",
    )
    _require(
        journal.get("kind") == "agent_log_migration_journal"
        and journal.get("phase") == "committed",
        "journal is not committed",
    )
    _require(
        _is_int(plan.get("body_mutation_count"))
        and plan["body_mutation_count"] == 0
        and _is_int(manifest.get("body_mutation_count"))
        and manifest["body_mutation_count"] == 0,
        "plan or manifest permits body mutation",
    )
    _require(
        plan.get("historical_claims_upgraded") is False
        and manifest.get("historical_claims_upgraded") is False,
        "plan or manifest upgrades historical claims",
    )
    root_identity = plan.get("root_identity")
    _require(isinstance(root_identity, dict), "plan root identity is missing")
    _require(
        set(root_identity) == {"resolved_path", "device", "inode", "sha256"},
        "plan root identity is not the exact schema-v1 projection",
    )
    root_basis = {
        field: root_identity.get(field)
        for field in ("resolved_path", "device", "inode")
    }
    _require(
        isinstance(root_basis["resolved_path"], str)
        and _is_int(root_basis["device"])
        and _is_int(root_basis["inode"]),
        "plan root identity is malformed",
    )
    _require(
        root_identity.get("sha256") == _sha256(_canonical_json(root_basis)),
        "plan root identity hash mismatch",
    )
    _require(
        journal.get("root_identity") == root_identity,
        "journal root identity binding mismatch",
    )
    plan_status = plan.get("status_map")
    plan_source = plan.get("source_index")
    _require(isinstance(plan_status, dict), "plan status-map binding is malformed")
    _require(isinstance(plan_source, dict), "plan source-index binding is malformed")
    _require(
        set(plan_status)
        == {"ref", "sha256", "schema_version", "mapping_policy_id", "version"},
        "plan status-map binding is not the exact schema-v1 projection",
    )
    _require(
        set(plan_source) == {"path", "sha256", "size", "raw_row_count"},
        "plan source-index binding is not the exact schema-v1 projection",
    )
    _require(
        _is_int(plan_status.get("schema_version"))
        and plan_status["schema_version"] == 1,
        "plan status-map schema version is malformed",
    )
    return root_identity, plan_status, plan_source
