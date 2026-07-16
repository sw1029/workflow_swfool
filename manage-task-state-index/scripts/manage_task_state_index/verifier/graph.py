"""Coordinate independent migration graph verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .bundle import _canonical_document, _external_mapping, _load_bundle
from .core import _canonical_json, _opaque_identity_token, _sha256
from .ledger_verification import _parse_current_ledger
from .plan_verification import _rebuild_plan, _validate_plan_shapes
from .publication_documents import (
    _journal_document,
    _marker_document,
    _prepare_document,
    _receipt_document,
)
from .publication_verification import _phase_receipt_sha256, _verify_publication
from .recovery_boundary import inspect_transaction_boundary
from .recovery_fingerprints import (
    _boundary_observation_sha256,
    _owned_write_set_sha,
)
from .recovery_validation import verify_recovery_observation

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

__all__ = [
    "_boundary_observation_sha256",
    "_canonical_document",
    "_external_mapping",
    "_journal_document",
    "_load_bundle",
    "_marker_document",
    "_parse_current_ledger",
    "_phase_receipt_sha256",
    "_prepare_document",
    "_rebuild_plan",
    "_receipt_document",
    "_validate_plan_shapes",
    "_verify_publication",
    "inspect_transaction_boundary",
    "verify_migration",
]
